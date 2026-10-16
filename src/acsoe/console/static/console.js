/*
 * The console's only script. Specs 23 and 24.
 *
 * Vanilla JavaScript, no framework, no npm, no build step, and nothing fetched
 * from a third party. It does four things and refuses to do a fifth:
 *
 * 1. Opens the WebSocket at /ws and applies each pushed payload to the DOM.
 * 2. Fetches the four screen endpoints ONCE, when the socket opens, for the
 *    page's first content. That is not polling: there is no timer on it and it
 *    never runs again except after a reconnect. A browser-side polling fallback
 *    is exactly what spec 23 forbids, because it quietly replaces the design
 *    with the thing the design rejected.
 * 3. Shows the disconnected state and reconnects with backoff. A dropped socket
 *    is a visible state, never a silently frozen screen.
 * 4. POSTs one of three commands, with a confirmation step on close_all.
 *
 * The one permitted motion is a 200ms background flash on a value that has
 * ACTUALLY changed, applied by adding the `flash` class. The duration and the
 * reduced-motion opt-out both live in CSS, so `@media (prefers-reduced-motion:
 * reduce)` drops the animation without this file knowing anything about it.
 * Nothing here animates a number continuously: continuous animation hides real
 * changes among fake ones.
 *
 * There is no interval literal in this file. The server owns the poll cadence,
 * reads it from config on every iteration, and this page never polls at all, so
 * neither `console.poll_interval_ms` nor `console.stale_after_ms` has a copy
 * here. Staleness arrives already decided, on every figure that has an age.
 */

(function () {
  "use strict";

  /* Reconnect backoff. These are not the poll interval and have nothing to do
     with it: they govern how hard a page retries a socket the server is not
     answering, which is a browser concern with no config key. Doubling from a
     second to half a minute means a console left open against a stopped daemon
     retries about ten times an hour rather than sixty times a minute. */
  var RECONNECT_MIN_MS = 1000;
  var RECONNECT_MAX_MS = 30000;

  var FLASH_CLASS = "flash";
  var STALE_CLASS = "stale";

  var socket = null;
  var reconnectDelay = RECONNECT_MIN_MS;
  var reconnectTimer = null;
  var pendingConfirm = null;

  /* ------------------------------------------------------------------ utils */

  function byField(name) {
    return document.querySelector('[data-field="' + name + '"]');
  }

  function byRows(name) {
    return document.querySelector('[data-rows="' + name + '"]');
  }

  function byEmpty(name) {
    return document.querySelector('[data-empty="' + name + '"]');
  }

  function cell(text, classes) {
    var td = document.createElement("td");
    td.textContent = text === null || text === undefined ? "" : String(text);
    if (classes) {
      td.className = classes;
    }
    return td;
  }

  /* A row is built from an array of [text, classes] pairs so every table below
     reads as data rather than as twelve lines of createElement. */
  function row(cells) {
    var tr = document.createElement("tr");
    for (var i = 0; i < cells.length; i += 1) {
      tr.appendChild(cell(cells[i][0], cells[i][1]));
    }
    return tr;
  }

  /* Set a value, and flash only if it actually changed. The comparison is against
     what is on the screen, so a redundant push - which happens once, when the
     load-time fetch overtook the socket's baseline - is silent. */
  function setText(element, value) {
    if (!element) {
      return;
    }
    var next = value === null || value === undefined ? "" : String(value);
    if (element.textContent === next) {
      return;
    }
    element.textContent = next;
    element.classList.remove(FLASH_CLASS);
    /* Reading offsetWidth restarts the animation on an element that is already
       mid-flash. Without it a value changing twice in quick succession flashes
       once, which is the opposite of what the flash is for. */
    void element.offsetWidth;
    element.classList.add(FLASH_CLASS);
  }

  /* Rule 5: a figure older than console.stale_after_ms renders at 50% opacity
     with its age beside it. The verdict and the age text are both computed
     server-side against the injected clock and arrive on the payload; this only
     applies them, so the browser's own clock never enters into it. */
  function applyStaleness(element, staleness) {
    if (!element) {
      return;
    }
    var age = element.parentNode
      ? element.parentNode.querySelector(".age")
      : null;
    if (!staleness || !staleness.is_stale) {
      element.classList.remove(STALE_CLASS);
      if (age) {
        age.textContent = "";
      }
      return;
    }
    element.classList.add(STALE_CLASS);
    if (age) {
      age.textContent = staleness.age_text;
    }
  }

  function fill(name, rows, builder) {
    var body = byRows(name);
    var empty = byEmpty(name);
    if (!body) {
      return;
    }
    body.textContent = "";
    for (var i = 0; i < rows.length; i += 1) {
      body.appendChild(builder(rows[i]));
    }
    if (empty) {
      empty.hidden = rows.length > 0;
    }
    var table = body.closest ? body.closest("table") : null;
    if (table) {
      table.hidden = rows.length === 0;
    }
  }

  function count(name, n, noun) {
    setText(byField(name), n === 0 ? "none" : n + " " + noun + (n === 1 ? "" : "s"));
  }

  /* ------------------------------------------------------- status and positions */

  function applyState(payload) {
    var band = payload.band;
    setText(byField("balance"), band.balance_text + (band.currency ? " " + band.currency : ""));
    // Whose money the figure is (D11). The words are computed server-side, like every
    // other reading in the band, so the page never decides what the number means.
    setText(byField("balance-label"), band.balance_label);
    setText(byField("mode"), band.mode.charAt(0).toUpperCase() + band.mode.slice(1));
    setText(byField("state"), band.state);
    setText(byField("data-age"), band.data_staleness ? band.data_staleness.age_text : "");
    applyStaleness(byField("balance"), band.staleness);
    applyStaleness(byField("data-age"), band.data_staleness);

    /* The open-positions region is rendered only when a position exists.
       ui-context.md puts it behind that for the same reason the cycle feed's
       empty state is prose: an empty table is furniture, not information. */
    var region = document.querySelector('[data-region="positions"]');
    if (region) {
      region.hidden = payload.positions.length === 0;
    }
    count("position-count", payload.positions.length, "position");
    fill("positions", payload.positions, function (p) {
      var tr = row([
        [p.pair, ""],
        [p.qty_text, "num"],
        [p.entry_price_text, "num"],
        /* `aged` names the three figures that come from the daemon's last touch
           of this row, which is what `staleness` is measured from. It carries no
           style of its own - it is how the staleness below finds them without
           counting columns, so inserting a column cannot silently fade the wrong
           cell. */
        [p.last_price_text, "num aged"],
        [p.target_price_text, "num"],
        [p.stop_price_text, "num"],
        [p.unrealised_pnl_text, "num aged " + p.direction],
        [p.unrealised_pnl_pct_text, "num aged " + p.direction],
        /* Spec 101. Rendered, never computed: the age arrives as text from the
           reader, which holds the console's one clock. Deriving it here from
           opened_at would read the *browser's* clock, which belongs to neither
           the daemon nor the console and is the one nobody controls. */
        [p.age_text, "num"],
        /* Spec 101. Already prose when it arrives. The page never maps a reason
           code: console/format.py is the one place that happens, and a code on
           screen is a log line shown to an operator. */
        [p.hold_reason_text, ""]
      ]);

      /* Rule 5, on the position row. The reader has decided the verdict and
         written the age since Phase 1 and the payload has carried both; nothing
         applied them, so a row the daemon had not touched for an hour rendered at
         full opacity beside a fresh one. applyStaleness is reused rather than
         reimplemented - rule 5 gets one implementation - and it finds the .age
         span through the cell's parent row.

         Three cells and not the whole row. `staleness` is measured from
         `updated_at`, so it ages exactly the figures that update: the mark, and
         the two unrealised figures computed from it. The entry, target and stop
         were decided at the fill and are still exactly true; fading them would say
         the position is doubtful when what is old is one number. Fading the whole
         row would be worse - `age_us` says a long-held position is hours old, so a
         row faded on the position's age would sit at half opacity permanently,
         which is the failure ui-context.md names for a slow poll interval. */
      var aged = tr.querySelectorAll(".aged");
      if (aged.length) {
        /* The age goes beside the mark alone - three copies of one age is noise,
           and rule 5 asks for the age of the figure, not of every column. It is
           created before the loop because applyStaleness writes into it. */
        aged[0].appendChild(document.createElement("span")).className = "age";
      }
      /* ONE call site, and the verdict is its argument. An earlier version faded
         the mark through applyStaleness and the other two through their own
         classList.toggle, which is two places for rule 5 to be decided - and the
         mutation that passed `null` here survived the whole console suite,
         because a test can see that applyStaleness is CALLED far more easily
         than it can see what it was handed. With one call the argument is the
         only thing to assert, and test_a_stale_position_row_is_faded_and_shows_
         its_age pins the call with p.staleness in it. */
      for (var a = 0; a < aged.length; a += 1) {
        applyStaleness(aged[a], p.staleness);
      }
      return tr;
    });
  }

  /* ------------------------------------------------------------------- feed */

  function applyFeed(payload) {
    count("feed-count", payload.rows.length, "entry");
    fill("feed", payload.rows, function (r) {
      return row([
        [r.time_text, ""],
        [r.pair === null ? "—" : r.pair, ""],
        [r.outcome, ""],
        [r.reason, ""]
      ]);
    });

    /* The empty state is the main state, and it is sent whether or not there are
       rows: it is what the system did, and it stays true when a handful of rows
       are showing. A stage whose count is null says so rather than showing a
       zero - a zero in a column of counts reads as a result. */
    var summary = document.querySelector('[data-region="feed-summary"]');
    if (!summary) {
      return;
    }
    setText(summary.querySelector('[data-field="feed-headline"]'), payload.summary.headline);
    var list = summary.querySelector('[data-rows="feed-stages"]');
    if (!list) {
      return;
    }
    list.textContent = "";
    for (var i = 0; i < payload.summary.stages.length; i += 1) {
      var stage = payload.summary.stages[i];
      var item = document.createElement("li");
      var label = document.createElement("span");
      label.textContent = stage.label;
      var value = document.createElement("span");
      value.className = "num";
      value.textContent = stage.count === null ? stage.detail : String(stage.count);
      item.appendChild(label);
      item.appendChild(value);
      list.appendChild(item);
    }
  }

  /* ---------------------------------------------------------------- history */

  function applyHistory(payload) {
    count("trade-count", payload.trades.length, "trade");
    count("rejection-count", payload.rejections.length, "rejection");
    fill("trades", payload.trades, function (t) {
      return row([
        [t.closed_text, ""],
        [t.pair, ""],
        [t.outcome, ""],
        [t.qty_text, "num"],
        [t.entry_price_text, "num"],
        [t.exit_price_text, "num"],
        [t.realised_pnl_text, "num " + t.direction],
        [t.realised_pnl_pct_text, "num " + t.direction]
      ]);
    });
    fill("rejections", payload.rejections, function (r) {
      return row([
        [r.time_text, ""],
        [r.pair, ""],
        [r.rejected_by_text, ""],
        [r.expected_move_pct_text, "num"],
        [r.friction_pct_text, "num"],
        [r.net_edge_pct_text, "num " + r.net_edge_direction],
        [r.hurdle_pct_text, "num"],
        [r.reason, ""]
      ]);
    });
  }

  /* --------------------------------------------------------------- research */

  function applyResearch(payload) {
    count("leaderboard-count", payload.leaderboard.length, "model");
    fill("leaderboard", payload.leaderboard, function (m) {
      return row([
        [m.model_id, ""],
        [m.model_version, ""],
        [m.fold === null ? "" : m.fold, "num"],
        [m.n_trades, "num"],
        [m.win_rate_text, "num"],
        [m.brier_text, "num"],
        [m.base_rate_brier_text, "num"],
        [m.effective_sample_size_text, "num"],
        [m.sharpe_text, "num"],
        [m.deflated_sharpe_text, "num"],
        [m.net_pnl_text, "num"],
        [m.promoted ? "Promoted" : "No", ""],
        [m.promotion_reason, ""]
      ]);
    });
    /* The SHAP pane is an empty state and nothing else. There is no row to draw
       and no chart to draw it on; the message names the phase that produces it. */
    setText(byEmpty("shap"), payload.shap.message);
  }

  function applyPayload(payload) {
    if (payload.state) {
      applyState(payload.state);
    }
    if (payload.feed) {
      applyFeed(payload.feed);
    }
    if (payload.history) {
      applyHistory(payload.history);
    }
    if (payload.research) {
      applyResearch(payload.research);
    }
  }

  /* ------------------------------------------------------ connection state */

  function showConnection(text, connected) {
    var element = byField("connection");
    if (!element) {
      return;
    }
    element.textContent = text;
    element.hidden = connected;
  }

  /* The first content on the page. Once, when the socket opens - never on a
     timer. The socket is opened FIRST and this runs on its `open` event, so the
     server's baseline watermark is already taken when these responses are built:
     a change in between produces one redundant push rather than a missed one. */
  function loadScreens() {
    var screens = [
      ["/api/state", applyState],
      ["/api/feed", applyFeed],
      ["/api/history", applyHistory],
      ["/api/research", applyResearch]
    ];
    screens.forEach(function (screen) {
      fetch(screen[0], { headers: { Accept: "application/json" } })
        .then(function (response) {
          if (!response.ok) {
            throw new Error(screen[0] + " answered " + response.status);
          }
          return response.json();
        })
        .then(screen[1])
        .catch(function (error) {
          showConnection(
            "Could not read " + screen[0] + ": " + error.message + ". Reload the page.",
            false
          );
        });
    });
  }

  function connect() {
    var scheme = window.location.protocol === "https:" ? "wss:" : "ws:";
    socket = new WebSocket(scheme + "//" + window.location.host + "/ws");

    socket.addEventListener("open", function () {
      reconnectDelay = RECONNECT_MIN_MS;
      showConnection("", true);
      loadScreens();
    });

    socket.addEventListener("message", function (event) {
      var payload;
      try {
        payload = JSON.parse(event.data);
      } catch (error) {
        return;
      }
      applyPayload(payload);
    });

    socket.addEventListener("close", function () {
      socket = null;
      scheduleReconnect();
    });

    /* An error is always followed by a close, so the reconnect is scheduled
       there and only there. Doing it in both handlers opens two sockets. */
    socket.addEventListener("error", function () {
      showConnection("Live updates disconnected. Reconnecting.", false);
    });
  }

  function scheduleReconnect() {
    if (reconnectTimer !== null) {
      return;
    }
    var seconds = Math.round(reconnectDelay / 1000);
    showConnection(
      "Live updates disconnected. The figures below are from " +
        "the last update. Retrying in " +
        seconds +
        "s.",
      false
    );
    reconnectTimer = window.setTimeout(function () {
      reconnectTimer = null;
      reconnectDelay = Math.min(reconnectDelay * 2, RECONNECT_MAX_MS);
      connect();
    }, reconnectDelay);
  }

  /* ----------------------------------------------------------- the commands */

  /* close_all ends exposure, so it is confirmed - and the confirmation restates
     the action BY ITS OWN NAME. The button's text never changes: an action keeps
     its name through the whole flow, and a button that turned into "Confirm" or
     "Are you sure?" would be a different action as far as the operator is
     concerned. The confirmation is a separate control beside it. */
  function needsConfirmation(name) {
    return name === "close_all";
  }

  function showCommandMessage(text) {
    setText(byField("command-message"), text);
  }

  function send(name, button) {
    button.disabled = true;
    fetch("/api/command/" + name, { method: "POST" })
      .then(function (response) {
        return response.json().then(function (body) {
          return { ok: response.ok, body: body };
        });
      })
      .then(function (result) {
        if (!result.ok) {
          showCommandMessage(result.body.message);
          return;
        }
        /* Recorded, not applied. The mode changes when the orchestrator claims
           the row at the top of its next tick, and the status band shows it when
           it does. Saying otherwise would make this page lie about the daemon. */
        showCommandMessage(result.body.message);
      })
      .catch(function (error) {
        showCommandMessage(
          "Could not write the command: " + error.message + ". The daemon has not been told. Try again."
        );
      })
      .then(function () {
        button.disabled = false;
      });
  }

  function clearConfirmation() {
    var confirmBar = document.querySelector('[data-region="confirm"]');
    if (confirmBar) {
      confirmBar.hidden = true;
    }
    pendingConfirm = null;
  }

  function askConfirmation(name, button) {
    var confirmBar = document.querySelector('[data-region="confirm"]');
    if (!confirmBar) {
      send(name, button);
      return;
    }
    pendingConfirm = { name: name, button: button };
    setText(
      confirmBar.querySelector('[data-field="confirm-question"]'),
      "Close all positions ends every open position and cancels every resting entry order. Confirm?"
    );
    confirmBar.hidden = false;
    var yes = confirmBar.querySelector('[data-confirm="yes"]');
    if (yes) {
      yes.focus();
    }
  }

  function wireCommands() {
    var buttons = document.querySelectorAll("[data-command]");
    for (var i = 0; i < buttons.length; i += 1) {
      buttons[i].disabled = false;
      buttons[i].addEventListener("click", function (event) {
        var button = event.currentTarget;
        var name = button.getAttribute("data-command");
        clearConfirmation();
        if (needsConfirmation(name)) {
          askConfirmation(name, button);
        } else {
          send(name, button);
        }
      });
    }

    var yes = document.querySelector('[data-confirm="yes"]');
    if (yes) {
      yes.addEventListener("click", function () {
        var pending = pendingConfirm;
        clearConfirmation();
        if (pending) {
          send(pending.name, pending.button);
        }
      });
    }
    var no = document.querySelector('[data-confirm="no"]');
    if (no) {
      no.addEventListener("click", function () {
        clearConfirmation();
        showCommandMessage("Nothing was written.");
      });
    }
  }

  function start() {
    clearConfirmation();
    wireCommands();
    connect();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start);
  } else {
    start();
  }
})();
