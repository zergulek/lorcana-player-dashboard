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
