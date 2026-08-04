const $ = (selector) => document.querySelector(selector);

const capitalizeFirst = (value = "") => {
  const characters = Array.from(String(value));
  return characters.length
    ? characters[0].toLocaleUpperCase() + characters.slice(1).join("")
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
    : `${metric === 1 ? "item" : "items"} in inventory${
        inventory?.available_items != null
          ? ` · ${inventory.available_items} available now`
          : ""
      }`;

  const bottomSection = `<form class="dash-scan-form" id="lendery-scan-form">
        <label for="lendery-scan-input">Scan an item barcode</label>
        <input type="text" id="lendery-scan-input" autocomplete="off" autofocus placeholder="Scan or type a barcode…" />
      </form>`;

  return `<div class="dash-card dash-card-feature dash-lendery is-link">
    <a class="dash-card-linkarea" href="/lendery" aria-label="Open Lendery inventory">
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
    </a>
    ${bottomSection}
    <a class="dash-card-cta" href="/lendery">Open inventory <b aria-hidden="true">→</b></a>
  </div>`;
};

const meetingCountdown = (meeting) => {
  if (meeting.days_until === 0) {
    return `<div class="live-metric meeting-countdown is-today"><strong>Today</strong><span>Next meeting</span></div>`;
  }
  return `<div class="live-metric meeting-countdown"><strong>${meeting.days_until}</strong><span>${meeting.days_until === 1 ? "day" : "days"}<small>until next meeting</small></span></div>`;
};

const bookclubCard = (tools, summary) => {
  const bookclub = summary?.bookclub;
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

const QUICK_ACTIONS = [
  {
    key: "lendery-suggest-item",
    href: "/lendery?action=suggest-item",
    icon: "✦",
    label: "Suggest a Lendery item",
    description: "Recommend something useful to borrow",
  },
  {
    key: "lendery-add-item",
    href: "/lendery?action=add-item",
    icon: "＋",
    label: "Add a Lendery item",
    description: "Create a new inventory record",
    permission: "lendery_manage",
  },
  {
    key: "lendery-report-issue",
    href: "/lendery?action=report-issue",
    icon: "!",
    label: "Report an inventory issue",
    description: "Choose an item and log the problem",
    permission: "lendery_manage",
  },
  {
    key: "bookclub-add-member",
    href: "/bookclub?action=add-member",
    icon: "＋",
    label: "Add a book club member",
    description: "Add someone to the selected club",
  },
  {
    key: "bookclub-add-book",
    href: "/bookclub?action=add-book",
    icon: "＋",
    label: "Add a book",
    description: "Add a title to the selected club",
  },
];

const availableQuickActions = (tools) =>
  QUICK_ACTIONS.filter(
    (action) => !action.permission || tools.has(action.permission),
  );

const quickActionMarkup = (action) => `<a class="quick-action" href="${action.href}">
  <span class="quick-action-icon" aria-hidden="true">${action.icon}</span>
  <span><strong>${action.label}</strong><small>${action.description}</small></span>
  <b aria-hidden="true">→</b>
</a>`;

const quickActionsCard = (tools, selectedKeys) => {
  const available = availableQuickActions(tools);
  const selected = selectedKeys
    .map((key) => available.find((action) => action.key === key))
    .filter(Boolean)
    .slice(0, 4);
  const selectedSet = new Set(selected.map((action) => action.key));
  const actionMarkup = selected.length
    ? selected.map(quickActionMarkup).join("")
    : '<p class="quick-actions-empty">Choose the shortcuts that help you most.</p>';
  const choices = available
    .map(
      (action) => `<label class="quick-action-choice">
        <input type="checkbox" name="actions" value="${action.key}" ${selectedSet.has(action.key) ? "checked" : ""}/>
        <span class="quick-action-icon" aria-hidden="true">${action.icon}</span>
        <span><strong>${action.label}</strong><small>${action.description}</small></span>
      </label>`,
    )
    .join("");

  return `<section class="dash-card dash-quick-actions" aria-labelledby="quick-actions-heading">
    <div class="quick-actions-heading">
      <div><span class="dash-kicker">Shortcuts</span><h2 id="quick-actions-heading">Quick actions</h2></div>
      <button class="edit-quick-actions" type="button">Edit shortcuts</button>
    </div>
    <div class="quick-actions-grid">${actionMarkup}</div>
    <dialog class="quick-actions-dialog" id="quick-actions-dialog" aria-labelledby="quick-actions-dialog-title">
      <form id="quick-actions-form">
        <div class="quick-actions-dialog-heading">
          <div><span class="dash-kicker">Make it yours</span><h2 id="quick-actions-dialog-title">Choose quick actions</h2></div>
          <button type="button" class="quick-actions-close" data-close-quick-actions aria-label="Close">×</button>
        </div>
        <p>Select up to four shortcuts. Options that require Lendery edit access appear only when available to you.</p>
        <div class="quick-action-choices">${choices}</div>
        <p class="quick-actions-error" id="quick-actions-error" role="alert"></p>
        <div class="quick-actions-dialog-footer">
          <span id="quick-actions-count"></span>
          <div><button class="quiet-button" type="button" data-close-quick-actions>Cancel</button><button class="primary-button" type="submit">Save shortcuts</button></div>
        </div>
      </form>
    </dialog>
  </section>`;
};

const dashboardState = { user: null, summary: null, tools: null };

const updateQuickActionsSelection = () => {
  const form = $("#quick-actions-form");
  if (!form) return;
  const checked = [...form.querySelectorAll("input[name='actions']:checked")];
  const atLimit = checked.length >= 4;
  form.querySelectorAll("input[name='actions']").forEach((input) => {
    input.disabled = atLimit && !input.checked;
  });
  $("#quick-actions-count").textContent = `${checked.length} of 4 selected`;
  form.querySelector("button[type='submit']").disabled = checked.length === 0;
};

const refreshQuickActionsCard = () => {
  const card = $(".dash-quick-actions");
  card.outerHTML = quickActionsCard(
    dashboardState.tools,
    dashboardState.user.quick_actions,
  );
  initializeQuickActionsEditor();
};

const initializeQuickActionsEditor = () => {
  const dialog = $("#quick-actions-dialog");
  const form = $("#quick-actions-form");
  if (!dialog || !form) return;
  $(".edit-quick-actions").addEventListener("click", () => {
    updateQuickActionsSelection();
    dialog.showModal();
  });
  form.addEventListener("change", updateQuickActionsSelection);
  form.querySelectorAll("[data-close-quick-actions]").forEach((button) => {
    button.addEventListener("click", () => dialog.close());
  });
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const selected = [
      ...form.querySelectorAll("input[name='actions']:checked"),
    ].map((input) => input.value);
    const saveButton = form.querySelector("button[type='submit']");
    const errorMessage = $("#quick-actions-error");
    errorMessage.textContent = "";
    saveButton.disabled = true;
    try {
      const result = await request("/auth/quick-actions", {
        method: "PUT",
        body: JSON.stringify({ actions: selected }),
      });
      dashboardState.user.quick_actions = result.quick_actions;
      dialog.close();
      refreshQuickActionsCard();
      toast("Quick actions updated.");
    } catch (error) {
      errorMessage.textContent = error.message;
      saveButton.disabled = false;
    }
  });
};

const quoteCard = () => `<section class="dash-card dash-quote-card" aria-labelledby="dashboard-quote-heading">
  <div class="dash-quote-heading">
    <div><span class="dash-kicker">From the shelves</span><h2 id="dashboard-quote-heading">A little literary pause</h2></div>
    <span class="dash-quote-mark" aria-hidden="true">“</span>
  </div>
  <div class="dash-quote-copy" id="dashboard-quote-copy" aria-live="polite">
    <blockquote id="dashboard-quote-text"></blockquote>
    <div class="dash-quote-footer">
      <cite><span id="dashboard-quote-title"></span><small id="dashboard-quote-author"></small></cite>
      <button id="next-dashboard-quote" type="button">Another quote <span aria-hidden="true">→</span></button>
    </div>
  </div>
</section>`;

const initializeDashboardQuotes = () => {
  const quotes = (window.bookQuotes || []).filter(
    (quote) => quote.quote.length <= 320,
  );
  const card = $(".dash-quote-card");
  if (!quotes.length) {
    card.hidden = true;
    return;
  }

  const copy = $("#dashboard-quote-copy");
  let index = Math.floor(Math.random() * quotes.length);
  const renderQuote = (animate = true) => {
    const update = () => {
      const quote = quotes[index];
      $("#dashboard-quote-text").textContent = quote.quote;
      $("#dashboard-quote-title").textContent = quote.title;
      $("#dashboard-quote-author").textContent = quote.author;
      copy.classList.remove("is-swapping");
    };
    if (!animate) return update();
    copy.classList.add("is-swapping");
    window.setTimeout(update, 240);
  };
  const nextQuote = () => {
    index = (index + 1) % quotes.length;
    renderQuote();
  };

  renderQuote(false);
  $("#next-dashboard-quote").addEventListener("click", nextQuote);
  if (quotes.length > 1) window.setInterval(nextQuote, 12000);
};

const renderDashboard = (user, summary) => {
  const displayName = capitalizeFirst(user.name);
  $("#welcome-heading").textContent = `${timeOfDayGreeting()}, ${displayName}`;
  $("#dashboard-account-name").textContent = displayName;
  $("#dashboard-account-username").textContent = `@${user.username}`;
  $("#admin-link").hidden = user.role !== "admin";
  const tools = new Set(user.tools);
  if (user.role === "admin") {
    tools.add("bookclub");
    tools.add("lendery_manage");
  }
  dashboardState.user = user;
  dashboardState.summary = summary;
  dashboardState.tools = tools;
  $("#tool-grid").innerHTML = [
    lenderyCard(tools, summary),
    bookclubCard(tools, summary),
    quickActionsCard(tools, user.quick_actions || []),
    quoteCard(),
  ].join("");
  initializeDashboardQuotes();
  initializeLenderyScan();
  initializeQuickActionsEditor();
};

const initializeLenderyScan = () => {
  const form = $("#lendery-scan-form");
  if (!form) return;
  const input = $("#lendery-scan-input");
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const barcode = input.value.trim();
    if (!barcode) return;
    location.href = `/lendery?barcode=${encodeURIComponent(barcode)}`;
  });
  input.focus({ preventScroll: true });
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
