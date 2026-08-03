const $ = (selector) => document.querySelector(selector);

const escapeHtml = (value = "") =>
  String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");

const formatUsername = (value = "") => {
  const characters = Array.from(String(value));
  return characters.length
    ? characters[0].toLocaleUpperCase() +
        characters.slice(1).join("").toLocaleLowerCase()
    : "";
};

const timeOfDayGreeting = (date = new Date()) => {
  const hourPart = new Intl.DateTimeFormat("en-CA", {
    hour: "numeric",
    hourCycle: "h23",
    timeZone: "America/Toronto",
  })
    .formatToParts(date)
    .find((part) => part.type === "hour");
  const hour = hourPart ? Number(hourPart.value) : date.getHours();
  if (hour >= 5 && hour < 12) return "Good morning";
  if (hour < 17) return "Good afternoon";
  if (hour < 22) return "Good evening";
  return "Good night";
};

const request = async (url, options = {}) => {
  const response = await fetch(url, {
    ...options,
    cache: "no-store",
    headers: {
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...options.headers,
    },
  });
  if (response.status === 204) return null;
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw Object.assign(
      new Error(
        typeof body.detail === "string"
          ? body.detail
          : body.detail?.[0]?.msg || "Something went wrong.",
      ),
      { status: response.status },
    );
  }
  return body;
};

const toast = (message) => {
  const element = $("#toast");
  element.textContent = message;
  element.classList.add("show");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => element.classList.remove("show"), 2600);
};

const formatDate = (value) =>
  new Intl.DateTimeFormat(undefined, {
    weekday: "short",
    month: "short",
    day: "numeric",
  }).format(new Date(`${value}T12:00:00`));

const lenderyCard = (tools, summary) => {
  const editor = tools.has("lendery_manage");
  const inventory = summary?.lendery;
  const metric = editor ? inventory?.attention_count : inventory?.total_items;
  const liveCopy = editor
    ? metric === 0
      ? "All caught up"
      : `${metric === 1 ? "item needs" : "items need"} attention`
    : `${metric === 1 ? "item" : "items"} in inventory`;

  return `<a class="dash-card dash-card-feature dash-lendery is-link" href="/lendery" aria-label="Open Lendery inventory">
    <div class="dash-card-top">
      <div class="dash-card-identity">
        <span class="dash-card-icon"><img src="/static/assets/lendery-logo-symbol-v3.png?v=4" alt=""/></span>
        <div><span class="dash-kicker">Live inventory</span><h2>Lendery</h2></div>
      </div>
      <span class="status">${editor ? "Editor" : "Viewer"}</span>
    </div>
    <div class="live-metric ${editor && metric === 0 ? "is-clear" : ""}">
      <strong>${metric ?? "—"}</strong>
      <span>${inventory ? escapeHtml(liveCopy) : "Live update unavailable"}</span>
    </div>
    <div class="dashboard-facts">
      <span><strong>${inventory?.total_items ?? "—"}</strong> Total items</span>
      <span><strong>${inventory?.checked_out_items ?? "—"}</strong> Checked out</span>
    </div>
    <span class="dash-card-cta">Open inventory <b aria-hidden="true">→</b></span>
  </a>`;
};

const meetingCountdown = (meeting) => {
  if (meeting.days_until === 0) {
    return `<div class="live-metric meeting-countdown is-today"><strong>Today</strong><span>Next meeting</span></div>`;
  }
  return `<div class="live-metric meeting-countdown"><strong>${meeting.days_until}</strong><span>${meeting.days_until === 1 ? "day" : "days"}<small>until next meeting</small></span></div>`;
};

const bookclubCard = (tools, summary) => {
  const bookclub = summary?.bookclub;
  const hasAccess = bookclub?.has_access ?? tools.has("bookclub");
  if (!hasAccess) {
    return `<div class="dash-card dash-card-feature dash-bookclub locked">
      <div class="dash-card-top">
        <div class="dash-card-identity">
          <span class="dash-card-icon"><img src="/static/assets/book-club-manager-logo-v2.png?v=1" alt=""/></span>
          <div><span class="dash-kicker">Reading community</span><h2>Book Club Manager</h2></div>
        </div>
        <span class="status muted">No access</span>
      </div>
      <div class="live-empty"><strong>Not assigned</strong><span>Ask an administrator for Book Club Manager access.</span></div>
      <span class="dash-card-cta">Access required</span>
    </div>`;
  }

  const meeting = bookclub?.next_meeting;
  const meetingDetails = meeting
    ? `${meetingCountdown(meeting)}
       <div class="meeting-preview">
         <span class="meeting-date">${escapeHtml(formatDate(meeting.meeting_date))}</span>
         <strong>${escapeHtml(meeting.book_title)}</strong>
         <p>${escapeHtml(meeting.club_name)}</p>
         <div class="meeting-meta">
           ${meeting.meeting_time ? `<span>${escapeHtml(meeting.meeting_time)}</span>` : ""}
           ${meeting.location ? `<span>${escapeHtml(meeting.location)}</span>` : ""}
         </div>
       </div>`
    : `<div class="live-empty"><strong>No meeting scheduled</strong><span>${bookclub ? `${bookclub.club_count} ${bookclub.club_count === 1 ? "club" : "clubs"} ready for planning.` : "Live update unavailable"}</span></div>`;

  return `<a class="dash-card dash-card-feature dash-bookclub is-link" href="/bookclub" aria-label="Open Book Club Manager">
    <div class="dash-card-top">
      <div class="dash-card-identity">
        <span class="dash-card-icon"><img src="/static/assets/book-club-manager-logo-v2.png?v=1" alt=""/></span>
        <div><span class="dash-kicker">Up next</span><h2>Book Club Manager</h2></div>
      </div>
      <span class="status on-dark">${bookclub?.club_count ?? "—"} ${bookclub?.club_count === 1 ? "club" : "clubs"}</span>
    </div>
    ${meetingDetails}
    <span class="dash-card-cta">Open manager <b aria-hidden="true">→</b></span>
  </a>`;
};

const quickActionsCard = (tools, summary) => {
  const actions = [];
  if (tools.has("lendery_manage")) {
    actions.push(
      ["/lendery?action=add-item", "＋", "Add a Lendery item", "Create a new inventory record"],
      ["/lendery?action=report-issue", "!", "Report an inventory issue", "Choose an item and log the problem"],
    );
  }
  if (summary?.bookclub?.has_access ?? tools.has("bookclub")) {
    actions.push(
      ["/bookclub?action=add-member", "＋", "Add a book club member", "Add someone to the selected club"],
      ["/bookclub?action=add-book", "＋", "Add a book", "Add a title to the selected club"],
    );
  }

  const actionMarkup = actions.length
    ? actions
        .map(
          ([href, icon, label, description]) => `<a class="quick-action" href="${href}">
            <span class="quick-action-icon" aria-hidden="true">${icon}</span>
            <span><strong>${label}</strong><small>${description}</small></span>
            <b aria-hidden="true">→</b>
          </a>`,
        )
        .join("")
    : '<p class="quick-actions-empty">No creation actions are available for your current access.</p>';

  return `<section class="dash-card dash-quick-actions" aria-labelledby="quick-actions-heading">
    <div class="quick-actions-heading"><div><span class="dash-kicker">Shortcuts</span><h2 id="quick-actions-heading">Quick actions</h2></div><span class="status muted">Your access</span></div>
    <div class="quick-actions-grid">${actionMarkup}</div>
  </section>`;
};

const renderDashboard = (user, summary) => {
  const displayName = formatUsername(user.username);
  $("#welcome-heading").textContent = `${timeOfDayGreeting()}, ${displayName}`;
  $("#dashboard-account-name").textContent = displayName;
  $("#admin-link").hidden = user.role !== "admin";
  const tools = new Set(user.tools);
  if (user.role === "admin") {
    tools.add("bookclub");
    tools.add("lendery_manage");
  }
  $("#tool-grid").innerHTML = [
    lenderyCard(tools, summary),
    bookclubCard(tools, summary),
    quickActionsCard(tools, summary),
  ].join("");
};

$("#logout").addEventListener("click", async () => {
  await request("/auth/logout", { method: "POST" });
  location.href = "/login";
});

(async () => {
  try {
    const user = await request("/auth/me");
    let summary = null;
    try {
      summary = await request("/auth/dashboard-summary");
    } catch (error) {
      toast(error.message);
    }
    renderDashboard(user, summary);
  } catch (error) {
    if (error.status === 401) {
      location.href = "/login";
      return;
    }
    toast(error.message);
  }
})();
