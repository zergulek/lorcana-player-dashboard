let DATA = null;
let selected = null;

const $ = s => document.querySelector(s);

function esc(v) {
  return String(v ?? "").replace(
    /[&<>"']/g,
    m => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;"
    }[m])
  );
}

function record(p) {
  return `${p.match_wins ?? 0}-${p.match_losses ?? 0}`;
}

function renderList() {
  const q = ($("#search").value || "").toLowerCase();

  const list = (DATA.players || [])
    .filter(p =>
      p.name.toLowerCase().includes(q)
    );

  $("#playerList").innerHTML =
    list.map(p => `
      <button
        class="player ${selected === p.name ? "active" : ""}"
        data-name="${esc(p.name)}"
      >
        <div class="pname">${esc(p.name)}</div>

        <div class="sub">
          <span>${esc(p.tag || "")}</span>
          <span>
            ${record(p)} · ${p.points ?? 0} pts
          </span>
        </div>
      </button>
    `).join("") ||
    '<div class="empty">No tracked players found.</div>';

  document.querySelectorAll(".player")
    .forEach(b =>
      b.addEventListener("click", () => {
        selected = b.dataset.name;
        renderList();
        renderProfile();
      })
    );
}

function renderProfile() {
  const p = (DATA.players || [])
    .find(x => x.name === selected);

  if (!p) {
    $("#profile").innerHTML =
      '<div class="empty">Select a player.</div>';
    return;
  }

  const totalGames =
    (p.game_wins ?? 0) +
    (p.game_losses ?? 0);

  const wr = totalGames
    ? Math.round(
        100 * p.game_wins / totalGames
      )
    : 0;

  const matches = p.matches || [];

  $("#profile").innerHTML = `
    <div class="eyebrow">
      ${esc(p.tag || "TRACKED PLAYER")}
    </div>

    <h2>${esc(p.name)}</h2>

    <div class="muted">
      ${esc(p.status || "")}
    </div>

    <div class="profilegrid">

      <div class="metric">
        <b>${record(p)}</b>
        <span>MATCH RECORD</span>
      </div>

      <div class="metric">
        <b>${p.points ?? 0}</b>
        <span>POINTS</span>
      </div>

      <div class="metric">
        <b>#${p.rank ?? "—"}</b>
        <span>RANK</span>
      </div>

      <div class="metric">
        <b>${wr}%</b>
        <span>GAME WIN RATE</span>
      </div>

    </div>

    <h3>Match history</h3>

    <div class="tablewrap">
      <table class="matches">

        <thead>
          <tr>
            <th>Round</th>
            <th>Opponent</th>
            <th>Result</th>
            <th>Score</th>
            <th>Table</th>
          </tr>
        </thead>

        <tbody>

          ${
            matches.length
              ? matches.map(m => `
                <tr>
                  <td>${esc(m.round)}</td>
                  <td>${esc(m.opponent)}</td>
                  <td class="${m.result === "W" ? "win" : "loss"}">
                    ${esc(m.result)}
                  </td>
                  <td>${esc(m.score || "—")}</td>
                  <td>${esc(m.table ?? "—")}</td>
                </tr>
              `).join("")
              : `
                <tr>
                  <td colspan="5" class="empty">
                    No match data yet.
                  </td>
                </tr>
              `
          }

        </tbody>
      </table>
    </div>
  `;
}

async function load() {
  try {
    const response = await fetch(
      `/api/event?t=${Date.now()}`,
      {
        cache: "no-store"
      }
    );

    if (!response.ok) {
      throw new Error(
        `HTTP ${response.status}`
      );
    }

    DATA = await response.json();

    if (DATA.error) {
      throw new Error(DATA.error);
    }

    const e = DATA.event || {};

    $("#eventName").textContent =
      e.name || "Lorcana Player Dashboard";

    $("#eventMeta").textContent =
      `Event ${e.id || "1007231"} · ${
        e.format || "Core Constructed"
      }`;

    $("#playerCount").textContent =
      e.players ?? "—";

    $("#trackedCount").textContent =
      (DATA.players || []).length;

    $("#roundName").textContent =
      e.current_round
        ? `R${e.current_round}`
        : "—";

    $("#updated").textContent =
      DATA.last_updated
        ? new Date(
            DATA.last_updated
          ).toLocaleTimeString(
            [],
            {
              hour: "2-digit",
              minute: "2-digit"
            }
          )
        : "—";

    if (
      !selected &&
      DATA.players?.length
    ) {
      selected = DATA.players[0].name;
    }

    renderList();
    renderProfile();

  } catch (err) {
    console.error(err);

    $("#profile").innerHTML = `
      <div class="empty">
        Unable to load tournament data.<br>
        <small>${esc(err.message)}</small>
      </div>
    `;
  }
}

$("#search")
  .addEventListener(
    "input",
    renderList
  );
function renderStandings() {
  const standings = DATA.standings || [];

  const container = $("#standings");

  if (!container) {
    return;
  }

  if (!standings.length) {
    container.innerHTML = `
      <div class="empty">
        Tournament standings are not available yet.
      </div>
    `;

    return;
  }

  const tracked = new Set(
    (DATA.players || []).map(
      p => p.name.toLowerCase()
    )
  );

  container.innerHTML = `
    <div class="tablewrap">
      <table class="standings">

        <thead>
          <tr>
            <th>Rank</th>
            <th>Player</th>
            <th>W</th>
            <th>L</th>
            <th>D</th>
            <th>Points</th>
            <th>GW</th>
            <th>GL</th>
          </tr>
        </thead>

        <tbody>

          ${standings.map((p, index) => {

            const name =
              p.name || "Unknown";

            const isTracked =
              tracked.has(
                name.toLowerCase()
              );

            return `
              <tr
                class="${isTracked ? "tracked" : ""}"
                data-standing-player="${esc(name)}"
              >

                <td>
                  ${p.rank ?? index + 1}
                </td>

                <td class="standing-name">
                  ${esc(name)}

                  ${
                    isTracked
                      ? '<span class="tracked-badge">TRACKED</span>'
                      : ''
                  }
                </td>

                <td>${p.wins ?? 0}</td>
                <td>${p.losses ?? 0}</td>
                <td>${p.draws ?? 0}</td>
                <td><b>${p.points ?? 0}</b></td>
                <td>${p.game_wins ?? 0}</td>
                <td>${p.game_losses ?? 0}</td>

              </tr>
            `;
          }).join("")}

        </tbody>

      </table>
    </div>
  `;

  document
    .querySelectorAll(
      "[data-standing-player]"
    )
    .forEach(row => {

      row.addEventListener(
        "click",
        () => {

          const name =
            row.dataset.standingPlayer;

          const trackedPlayer =
            (DATA.players || []).find(
              p =>
                p.name.toLowerCase() ===
                name.toLowerCase()
            );

          if (trackedPlayer) {
            selected =
              trackedPlayer.name;

            renderList();
            renderProfile();

            window.scrollTo({
              top: 0,
              behavior: "smooth"
            });
          }
        }
      );

    });
}

load();

setInterval(
  load,
  60 * 1000
);
