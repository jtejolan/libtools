const $ = (selector) => document.querySelector(selector);

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
    const detail = body.detail;
    throw Object.assign(
      new Error(typeof detail === "string" ? detail : detail?.[0]?.msg || "Something went wrong."),
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

const capitalizeFirst = (value = "") => {
  const characters = Array.from(String(value));
  return characters.length
    ? characters[0].toLocaleUpperCase() + characters.slice(1).join("")
    : "";
};

const timeBasedGreeting = (name, now = new Date()) => {
  const displayName = capitalizeFirst(String(name || "Reader").trim()) || "Reader";
  const hour = now.getHours();
  const greetings = hour < 5
    ? [
      `A late-night hello, ${displayName}`,
      `Still up reading, ${displayName}?`,
      `Burning the midnight oil, ${displayName}?`,
    ]
    : hour < 12
      ? [
        `Good morning, ${displayName}`,
        `Morning, ${displayName}—glad you’re here`,
        `Ready for a new chapter, ${displayName}?`,
      ]
      : hour < 17
        ? [
          `Good afternoon, ${displayName}`,
          `Nice to see you this afternoon, ${displayName}`,
          `Taking a reading break, ${displayName}?`,
        ]
        : hour < 22
          ? [
            `Good evening, ${displayName}`,
            `Welcome back this evening, ${displayName}`,
            `Time to settle in with the club, ${displayName}`,
          ]
          : [
            `A late-night hello, ${displayName}`,
            `Still up reading, ${displayName}?`,
            `One more chapter tonight, ${displayName}?`,
          ];
  const dailyIndex = (now.getFullYear() + now.getMonth() + now.getDate() + displayName.length) % greetings.length;
  return greetings[dailyIndex];
};

const formatDate = (value) =>
  new Intl.DateTimeFormat(undefined, { weekday: "short", month: "short", day: "numeric", year: "numeric" }).format(
    new Date(`${value}T12:00:00`),
  );

const render = (participant) => {
  document.title = `${participant.club_name} — Book Club`;
  $("#club-eyebrow").textContent = participant.club_name;
  $("#welcome-heading").textContent = timeBasedGreeting(participant.name);

  const panel = $("#email-panel");
  if (!participant.email_verified) {
    panel.hidden = false;
    $("#email-copy").textContent = `${participant.email} is waiting to be verified before it can be used for password resets.`;
  } else {
    panel.hidden = true;
  }
};

const participantState = {
  participant: null,
  participantId: null,
  books: [],
  library: { current: [], up_next: [], previously_read: [] },
  upcomingMeeting: null,
  latestCompletedMeeting: null,
  readingProgress: null,
  announcements: [],
  announcementCollapsed: false,
  latestAnnouncementId: null,
  announcementPollId: null,
  votingRound: null,
  datePoll: null,
  profile: null,
  activeBookId: null,
  activeBookDetail: null,
  clubActivity: [],
  bookHubTab: "conversation",
  portalView: "home",
  homeBookId: null,
  personalStats: null,
  clubStats: null,
  activeRating: null,
  heroRatingSaving: false,
  pendingReviewRating: 3,
};

const portalViewCopy = {
  books: ["The books that brought us here", "Our reading journey", "Follow the club from finished favourites to the book currently bringing everyone together."],
  personal: ["Your reading journey", "My stats", "A private view of the books, meetings, ratings, and choices that make up your club experience."],
  club: ["Reading together", "Our club story", "The books, tastes, and shared reactions shaping your reading community."],
  members: ["Your reading community", "Members", "Meet the readers who have chosen to appear in the club directory."],
};

const portalHeading = (view) => {
  const [eyebrow, title, intro] = portalViewCopy[view];
  return `<header class="portal-page-heading"><div><p class="eyebrow">${eyebrow}</p><h1>${title}</h1><p class="intro">${intro}</p></div></header>`;
};

const initializePortalShell = () => {
  const main = $("main.dashboard");
  const header = $(".site-header");
  const portalNavIcons = {
    home: '<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M15 21v-8a1 1 0 0 0-1-1h-4a1 1 0 0 0-1 1v8" /><path d="M3 10a2 2 0 0 1 .709-1.528l7-6a2 2 0 0 1 2.582 0l7 6A2 2 0 0 1 21 10v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" /></svg>',
    books: '<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 5v16" /><path d="M20.001 19A2 2 0 0022 17V5a2 2 0 00-1.999-2L16 3.002A5 5 0 0012 5a5 5 0 00-4-2H4a2 2 0 00-2 2v12a2 2 0 001.999 2H8a5 5 0 014 2 5 5 0 014-2z" /></svg>',
    personal: '<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8" /><path d="M3 3v5h5" /><path d="M12 7v5l4 2" /></svg>',
    club: '<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect width="7" height="7" x="3" y="3" rx="1" /><rect width="7" height="7" x="14" y="3" rx="1" /><rect width="7" height="7" x="14" y="14" rx="1" /><rect width="7" height="7" x="3" y="14" rx="1" /></svg>',
    members: '<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" /><path d="M16 3.128a4 4 0 0 1 0 7.744" /><path d="M22 21v-2a4 4 0 0 0-3-3.87" /><circle cx="9" cy="7" r="4" /></svg>',
  };
  header.insertAdjacentHTML("afterend", `<nav class="participant-portal-nav" aria-label="Participant portal">${[
    ["home", "Home"], ["books", "Books"], ["personal", "My stats"], ["club", "Club stats"], ["members", "Members"],
  ].map(([view, label]) => `<button type="button" data-portal-nav="${view}">${portalNavIcons[view]}<span>${label}</span></button>`).join("")}</nav>`);

  const home = document.createElement("section");
  home.className = "portal-view";
  home.dataset.portalView = "home";
  [".participant-heading", "#email-panel", ".participant-grid", "#book-page-section", ".decisions-disclosure", ".legacy-participant-sections"].forEach((selector) => home.append($(selector)));
  const homeBookSlot = document.createElement("div");
  homeBookSlot.id = "home-book-slot";
  home.insertBefore(homeBookSlot, home.querySelector("#book-page-section"));
  homeBookSlot.append(home.querySelector("#book-page-section"));

  const books = document.createElement("section");
  books.className = "portal-view";
  books.dataset.portalView = "books";
  books.innerHTML = portalHeading("books");
  const journeyOverview = document.createElement("section");
  journeyOverview.id = "books-journey-overview";
  journeyOverview.innerHTML = '<p class="muted">Loading the club’s reading journey…</p>';
  books.append(journeyOverview);
  books.append($("#library-section"));
  const libraryHeading = books.querySelector(".library-heading");
  libraryHeading.querySelector(".eyebrow").textContent = "Every chapter so far";
  libraryHeading.querySelector("h2").textContent = "Follow the shelf";
  libraryHeading.querySelector(".library-note").textContent = "Explore the full journey or narrow it to the part of the story you want to revisit.";
  const search = libraryHeading.querySelector("#library-search");
  const controls = document.createElement("div");
  controls.className = "library-controls";
  controls.innerHTML = '<select id="library-status-filter" aria-label="Filter books"><option value="all">All books</option><option value="current">Current</option><option value="up_next">Coming up</option><option value="previously_read">Previously read</option></select><select id="library-sort" aria-label="Sort books"><option value="journey">Club journey</option><option value="title">Title</option><option value="rating">Highest rated</option></select>';
  controls.prepend(search);
  libraryHeading.append(controls);
  const suggestion = document.createElement("section");
  suggestion.className = "book-suggestion-section is-collapsed";
  suggestion.innerHTML = '<button class="suggestion-launch" id="suggestion-launch" type="button" aria-expanded="false" aria-controls="suggestion-workspace"><span class="suggestion-launch-icon" aria-hidden="true"><svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14" /><path d="M12 5v14" /></svg></span><span><strong>Suggest a book</strong><small>Search for a title and send it to your facilitator.</small></span><b data-suggestion-launch-label>Open</b><svg class="icon suggestion-launch-chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m9 18 6-6-6-6" /></svg></button><div class="suggestion-workspace" id="suggestion-workspace" hidden><form class="google-book-search" id="google-book-search-form"><label for="google-book-query">Title, author, or ISBN</label><div class="suggestion-search-control"><svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="11" cy="11" r="8" /><path d="m21 21-4.3-4.3" /></svg><input id="google-book-query" type="search" autocomplete="off" placeholder="Start typing a title, author, or ISBN" role="combobox" aria-autocomplete="list" aria-controls="google-book-results" aria-expanded="false" /><div class="google-book-results" id="google-book-results" role="listbox" hidden></div></div><p class="google-book-status muted" id="google-book-status" aria-live="polite">Start typing to search.</p></form><div class="suggestion-preview" id="suggestion-preview" hidden></div></div>';
  journeyOverview.append(suggestion);

  const personal = document.createElement("section");
  personal.className = "portal-view";
  personal.dataset.portalView = "personal";
  personal.innerHTML = `${portalHeading("personal")}<div id="personal-stats-content"><p class="muted">Loading your reading journey…</p></div>`;
  const club = document.createElement("section");
  club.className = "portal-view";
  club.dataset.portalView = "club";
  club.innerHTML = `${portalHeading("club")}<div id="club-stats-content"><p class="muted">Loading club stats…</p></div>`;
  const members = document.createElement("section");
  members.className = "portal-view";
  members.dataset.portalView = "members";
  members.innerHTML = portalHeading("members");
  const membersSection = $(".members-section");
  membersSection.classList.add("directory-experience");
  membersSection.querySelector(".section-toolbar").innerHTML = '<div class="directory-community-copy"><span class="directory-community-mark" aria-hidden="true"><svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" /><path d="M16 3.128a4 4 0 0 1 0 7.744" /><path d="M22 21v-2a4 4 0 0 0-3-3.87" /><circle cx="9" cy="7" r="4" /></svg></span><div><p class="eyebrow">Opt-in community</p><h2>Meet the people behind the pages</h2><p>Reader profiles make discussions more personal. Email addresses and private club details are never shown.</p></div></div><button class="public-profile-button" id="edit-directory-profile" type="button">Edit my profile <span aria-hidden="true"><svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m9 18 6-6-6-6" /></svg></span></button>';
  members.append(membersSection);

  const book = document.createElement("section");
  book.className = "portal-view";
  book.dataset.portalView = "book";
  book.innerHTML = '<div class="book-detail-toolbar"><button class="quiet-button" id="book-detail-back" type="button"><svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m15 18-6-6 6-6" /></svg> Back to books</button><div class="book-detail-journey-nav" id="book-detail-journey-nav"></div></div><div id="book-detail-slot"></div>';
  main.replaceChildren(home, books, personal, club, members, book);
  document.body.insertAdjacentHTML("beforeend", '<dialog class="manage-dialog rating-review-dialog" id="rating-review-dialog"><form id="rating-review-form"><header class="rating-review-dialog-heading"><img id="rating-review-cover" alt="" /><div><p class="eyebrow">Your reading response</p><h2 id="rating-review-heading">Rate this book</h2><p id="rating-review-book"></p></div><button class="rating-review-close" type="button" data-close-rating-review aria-label="Close review window">×</button></header><div class="rating-review-body"><section class="review-rating-panel"><div><span class="hero-rating-label">Your rating</span><p>Choose a half or whole star.</p></div><div class="detail-rating-picker" id="rating-review-stars"></div></section><label class="review-writing-field"><span><strong>Your review</strong><small>Optional</small></span><p>Share what stayed with you, what challenged you, or what you would tell another reader.</p><textarea id="rating-review-text" rows="6" maxlength="4000" placeholder="Start writing your response…"></textarea><small class="review-sharing-note">Your review will appear alongside your rating in Ratings and Reviews.</small></label><p class="form-error" id="rating-review-error"></p></div><footer class="rating-review-footer"><p><span aria-hidden="true">◇</span> Shared with members of this book club</p><div><button class="quiet-button" type="button" data-close-rating-review>Cancel</button><button class="primary-button" type="submit">Save rating &amp; review</button></div></footer></form></dialog>');
};

initializePortalShell();

const formatTimestamp = (value) =>
  new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", year: "numeric" }).format(new Date(value));

const setPortalView = (view, { updateHistory = true } = {}) => {
  const selected = document.querySelector(`[data-portal-view="${view}"]`) ? view : "home";
  participantState.portalView = selected;
  document.querySelectorAll("[data-portal-view]").forEach((section) => { section.hidden = section.dataset.portalView !== selected; });
  document.querySelectorAll("[data-portal-nav]").forEach((button) => {
    const active = button.dataset.portalNav === selected || (selected === "book" && button.dataset.portalNav === "books");
    button.classList.toggle("active", active);
    if (active) button.setAttribute("aria-current", "page"); else button.removeAttribute("aria-current");
  });
  if (updateHistory && selected !== "book") history.pushState({ view: selected }, "", selected === "home" ? location.pathname : `${location.pathname}?view=${selected}`);
  window.scrollTo({ top: 0, behavior: "smooth" });
};

setPortalView("home", { updateHistory: false });

document.querySelector(".participant-portal-nav").addEventListener("click", (event) => {
  const button = event.target.closest("[data-portal-nav]");
  if (!button) return;
  if (button.dataset.portalNav === "home" && participantState.homeBookId) {
    openBookPage(participantState.homeBookId, { portalView: "home", updateHistory: true }).catch((error) => toast(error.message));
    return;
  }
  setPortalView(button.dataset.portalNav);
});

$("#book-detail-back").addEventListener("click", () => setPortalView("books"));

window.addEventListener("popstate", () => {
  const params = new URLSearchParams(location.search);
  const view = params.get("view") || "home";
  const bookId = params.get("book");
  if (view === "book" && bookId) openBookPage(bookId, { portalView: "book", updateHistory: false }).catch(() => setPortalView("books", { updateHistory: false }));
  else if (view === "home" && participantState.homeBookId) openBookPage(participantState.homeBookId, { portalView: "home", updateHistory: false }).catch(() => {});
  else setPortalView(view, { updateHistory: false });
});

const renderAnnouncements = (announcements) => {
  const previousLatestId = participantState.latestAnnouncementId;
  participantState.announcements = announcements;
  const latest = announcements[0];
  const unreadCount = announcements.filter((item) => !item.read).length;
  const isFirstLoad = previousLatestId == null;
  const hasNewUnread = latest && previousLatestId != null && latest.id !== previousLatestId && !latest.read;
  if (isFirstLoad) participantState.announcementCollapsed = !latest || latest.read;
  else if (hasNewUnread) participantState.announcementCollapsed = false;
  participantState.latestAnnouncementId = latest?.id ?? null;
  const section = $("#announcements-section");
  section.classList.toggle("is-collapsed", participantState.announcementCollapsed);
  section.classList.toggle("has-unread", unreadCount > 0);
  $("#announcement-toggle").setAttribute("aria-expanded", String(!participantState.announcementCollapsed));
  $("#announcement-toggle").textContent = participantState.announcementCollapsed ? "Expand" : latest && !latest.read ? "Mark read & minimize" : "Minimize";
  $("#announcement-unread-count").hidden = unreadCount === 0;
  $("#announcement-unread-count").textContent = `${unreadCount} unread`;
  $("#announcement-compact-copy").textContent = latest ? `${latest.title} · ${formatTimestamp(latest.published_at)}` : "No announcements right now";
  $("#announcements-content").innerHTML = announcements.length
    ? `<article class="user-card" style="align-items:start">
            <div>
              ${latest.pinned ? '<p class="eyebrow" style="margin-bottom:4px">Pinned</p>' : ""}
              <h3>${latest.read ? "" : '<span class="unread-dot" aria-label="Unread"></span>'}${escapeHtml(latest.title)}</h3>
              <p class="user-meta">${escapeHtml(formatTimestamp(latest.published_at))}</p>
              <p style="white-space:pre-wrap;margin:.6rem 0 0">${escapeHtml(latest.body)}</p>
            </div>
          </article>`
    : '<p class="muted">No announcements right now.</p>';
  $("#view-announcements").hidden = !announcements.length;
  $("#announcement-list").innerHTML = announcements.length
    ? announcements.map((item) => `<article data-announcement-id="${item.id}">
        <p class="eyebrow">${item.pinned ? "Pinned · " : ""}${item.read ? "Read" : "Unread"}</p>
        <h3>${item.read ? "" : '<span class="unread-dot" aria-hidden="true"></span>'}${escapeHtml(item.title)}</h3>
        <p class="user-meta">${escapeHtml(formatTimestamp(item.published_at))}</p>
        <p style="white-space:pre-wrap">${escapeHtml(item.body)}</p>
        ${item.read ? "" : `<button class="quiet-button" type="button" data-mark-announcement-read="${item.id}">Mark as read</button>`}
      </article>`).join("")
    : '<p class="muted">No announcements yet.</p>';
  renderActionCenter();
};

const loadAnnouncements = async () => renderAnnouncements(await request("/participant/announcements"));

const startAnnouncementRefresh = () => {
  if (participantState.announcementPollId) return;
  participantState.announcementPollId = window.setInterval(() => {
    if (document.visibilityState === "visible") loadAnnouncements().catch(() => {});
  }, 60000);
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") loadAnnouncements().catch(() => {});
  });
};

const actionButton = (label, target) => `<button class="secondary-button" type="button" data-scroll-target="${target}">${label}</button>`;

const renderActionCenter = () => {
  const actions = [];
  const participant = participantState.participant;
  if (participant && !participant.email_verified) actions.push(["Verify your email", "Secure password recovery and account updates.", "email-panel", "Verify email"]);
  if (participantState.upcomingMeeting && !participantState.upcomingMeeting.rsvp_status) actions.push(["RSVP for the next meeting", `Let the facilitator know about ${participantState.upcomingMeeting.meeting.book.title}.`, "rsvp-section", "Respond now"]);
  if (participantState.votingRound?.status === "open" && !participantState.votingRound.my_vote_candidate_id) actions.push(["Choose the next book", "A book vote is waiting for your response.", "voting-section", "Vote now"]);
  if (participantState.datePoll?.status === "open" && !participantState.datePoll.my_vote_option_id) actions.push(["Choose a meeting date", "A date poll is waiting for your response.", "date-poll-section", "Vote now"]);
  const completedBook = participantState.latestCompletedMeeting?.meeting?.book;
  if (completedBook && !ratingsState.mineByBook[completedBook.id]) actions.push([`Reflect on ${completedBook.title}`, "Rate the book or leave a short review after your meeting.", "library-section", "Share your take"]);
  $("#action-heading").textContent = actions.length ? `${actions.length} thing${actions.length === 1 ? "" : "s"} to do` : "You’re all caught up";
  $("#action-count").textContent = actions.length ? "Your choices are saved as you make them." : "Nothing needs a response right now.";
  $("#action-list").innerHTML = actions.map(([title, copy, target, label]) => `<div class="action-item"><strong>${escapeHtml(title)}</strong><span>${escapeHtml(copy)}</span>${actionButton(label, target)}</div>`).join("");
};

document.addEventListener("click", (event) => {
  const button = event.target.closest("[data-scroll-target]");
  if (!button) return;
  document.getElementById(button.dataset.scrollTarget)?.scrollIntoView({ behavior: "smooth", block: "start" });
});

$("#view-announcements").addEventListener("click", () => $("#announcements-dialog").showModal());
$("#announcement-toggle").addEventListener("click", async () => {
  if (participantState.announcementCollapsed) {
    participantState.announcementCollapsed = false;
    renderAnnouncements(participantState.announcements);
    return;
  }
  const latest = participantState.announcements[0];
  participantState.announcementCollapsed = true;
  try {
    if (latest && !latest.read) {
      await request(`/participant/announcements/${latest.id}/read`, { method: "PUT" });
      await loadAnnouncements();
    } else renderAnnouncements(participantState.announcements);
  } catch (error) {
    participantState.announcementCollapsed = false;
    renderAnnouncements(participantState.announcements);
    toast(error.message);
  }
});
$("#close-announcements-dialog").addEventListener("click", () => $("#announcements-dialog").close());
$("#announcement-list").addEventListener("click", async (event) => {
  const button = event.target.closest("[data-mark-announcement-read]");
  if (!button) return;
  try {
    await request(`/participant/announcements/${button.dataset.markAnnouncementRead}/read`, { method: "PUT" });
    await loadAnnouncements();
  } catch (error) { toast(error.message); }
});

const renderRsvp = (data) => {
  participantState.upcomingMeeting = data;
  const panel = document.querySelector("[data-book-meeting]");
  if (panel) panel.outerHTML = meetingHeroMarkup(data);
  renderActionCenter();
};

const meetingHeroMarkup = (data) => {
  if (!data) return `<section class="book-meeting-details" id="rsvp-section" data-book-meeting><p class="book-meeting-note">Your facilitator hasn’t scheduled the next gathering yet.</p></section>`;
  const meeting = data.meeting;
  const options = [
    ["attending", "I’m attending"],
    ["maybe", "Maybe"],
    ["not_attending", "Can’t attend"],
  ];
  return `<section class="book-meeting-details" id="rsvp-section" data-book-meeting>
    <div class="book-meeting-row">
      <div class="book-meeting-facts">
        <div class="book-meeting-fact"><span>Meeting</span><strong>${escapeHtml(formatDate(meeting.meeting_date))}${meeting.meeting_time ? ` · ${escapeHtml(meeting.meeting_time)}` : ""}</strong></div>
        <div class="book-meeting-fact"><span>Location</span><strong>${escapeHtml(meeting.location || "To be announced")}</strong></div>
      </div>
      ${data.video_call_url ? `<a class="calendar-link" href="${escapeHtml(data.video_call_url)}" target="_blank" rel="noopener">Join online <svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M15 3h6v6" /><path d="M10 14 21 3" /><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" /></svg></a>` : ""}
    </div>
    <div class="meeting-response-row"><span>Your RSVP</span><div class="meeting-actions">
      ${options.map(([status, label]) => `<button class="${data.rsvp_status === status ? "primary-button" : "secondary-button"}" data-rsvp="${status}" data-meeting-id="${meeting.id}">${label}</button>`).join("")}
    </div></div>
    <p class="book-meeting-note">${data.rsvp_status ? "Your RSVP is saved. You can change it anytime before the meeting." : "RSVP so your facilitator can plan."}</p>
    <div class="calendar-actions"><a class="calendar-link" href="${escapeHtml(data.google_calendar_url)}" target="_blank" rel="noopener">Add to Google Calendar <svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M15 3h6v6" /><path d="M10 14 21 3" /><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" /></svg></a><a class="calendar-link" href="${escapeHtml(data.ics_calendar_url)}" download><svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 15V3" /><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" /><path d="m7 10 5 5 5-5" /></svg> Download calendar invite</a></div>
  </section>`;
};

const progressLabels = { not_started: "Not started", reading: "Reading", finished: "Finished" };

const renderCurrentReading = (data, progress) => {
  const section = $("#current-reading-section");
  if (!data) { section.hidden = true; return; }
  const book = data.meeting.book;
  section.hidden = false;
  $("#current-reading-title").textContent = book.title;
  $("#current-reading-meta").textContent = `${book.author} · Discussing ${formatDate(data.meeting.meeting_date)}`;
  $("#current-book-detail").innerHTML = `${book.description ? `<p>${escapeHtml(book.description)}</p>` : '<p class="muted">No description has been added yet.</p>'}${book.page_count ? `<p class="user-meta">${book.page_count} pages${book.genres ? ` · ${escapeHtml(book.genres)}` : ""}</p>` : ""}${book.catalogue_url ? `<a class="calendar-link" href="${escapeHtml(book.catalogue_url)}" target="_blank" rel="noopener">Find it in the catalogue <svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M15 3h6v6" /><path d="M10 14 21 3" /><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" /></svg></a>` : ""}`;
  const cover = $("#current-reading-cover");
  cover.src = book.cover_image_url || "/static/assets/library-tools-logo-classic.svg?v=1";
  cover.alt = book.cover_image_url ? `Cover of ${book.title}` : "";
  $("#reading-progress-options").innerHTML = ["not_started", "reading", "finished"]
    .map((status) => `<button type="button" class="${progress?.status === status ? "primary-button" : "secondary-button"} progress-button" data-reading-status="${status}" data-book-id="${book.id}">${progressLabels[status]}</button>`)
    .join("") + `<button type="button" class="quiet-button" data-open-book="${book.id}">Book details &amp; club ratings</button>` + (progress?.status ? `<button type="button" class="quiet-button" data-reading-status="" data-book-id="${book.id}">Clear</button>` : "");
};

const loadCurrentReading = async (data = participantState.upcomingMeeting) => {
  if (!data) { renderCurrentReading(null, null); return; }
  participantState.readingProgress = await request(`/participant/books/${data.meeting.book.id}/reading-progress`);
  renderCurrentReading(data, participantState.readingProgress);
};

const loadRsvp = async () => {
  const data = await request("/participant/meetings/upcoming");
  participantState.upcomingMeeting = data;
  renderRsvp(data);
  await loadCurrentReading(data);
};

$("#reading-progress-options").addEventListener("click", async (event) => {
  const button = event.target.closest("[data-reading-status]");
  if (!button) return;
  try {
    participantState.readingProgress = await request(`/participant/books/${button.dataset.bookId}/reading-progress`, {
      method: "PUT",
      body: JSON.stringify({ status: button.dataset.readingStatus || null }),
    });
    renderCurrentReading(participantState.upcomingMeeting, participantState.readingProgress);
    await loadActivity();
    renderActionCenter();
    toast(button.dataset.readingStatus ? "Reading progress saved." : "Reading progress cleared.");
  } catch (error) { toast(error.message); }
});

$("#book-page-content").addEventListener("click", async (event) => {
  const button = event.target.closest("[data-rsvp]");
  if (!button) return;
  try {
    renderRsvp(await request(`/participant/meetings/${button.dataset.meetingId}/rsvp`, {
      method: "PUT",
      body: JSON.stringify({ status: button.dataset.rsvp }),
    }));
    toast("RSVP saved.");
    renderActionCenter();
  } catch (error) {
    toast(error.message);
  }
});

const renderVotingCandidate = (candidate, { showResults, myVoteId, isWinner }) => {
  const isMine = candidate.id === myVoteId;
  const countCopy = showResults && candidate.vote_count != null ? ` · ${candidate.vote_count} vote${candidate.vote_count === 1 ? "" : "s"}` : "";
  return `<article class="user-card" data-candidate-id="${candidate.id}">
    <div>
      <h3>${escapeHtml(candidate.book.title)}${isWinner ? " 🏆" : ""}</h3>
      <p class="user-meta">${escapeHtml(candidate.book.author)}${countCopy}${candidate.proposed_by_name ? ` · proposed by ${escapeHtml(candidate.proposed_by_name)}` : ""}</p>
    </div>
    <div class="user-actions">
      ${
        showResults
          ? ""
          : `<button class="${isMine ? "primary-button" : "secondary-button"}" data-vote-candidate="${candidate.id}">${isMine ? "Your vote" : "Vote"}</button>`
      }
    </div>
  </article>`;
};

const renderVoting = (round) => {
  participantState.votingRound = round;
  const content = $("#voting-content");
  if (!round) {
    $("#voting-heading").textContent = "Voting";
    content.innerHTML = '<p class="muted">No vote is open right now. Check back soon.</p>';
    renderActionCenter();
    return;
  }
  const approved = round.candidates.filter((c) => c.status === "approved");
  const myPending = round.candidates.filter(
    (c) => c.status === "pending" && c.proposed_by_participant_id === participantState.participantId,
  );
  const showResults = round.status === "closed";
  $("#voting-heading").textContent = showResults ? "Results" : "Cast your vote";

  const proposedBookIds = new Set(round.candidates.map((c) => c.book.id));
  const proposableBooks = participantState.books.filter((book) => !proposedBookIds.has(book.id));
  const proposeForm = showResults || !proposableBooks.length
    ? ""
    : `<form id="propose-candidate-form" class="dash-scan-form">
        <label for="propose-book-select">Propose another book</label>
        <div style="display:flex;gap:8px;margin-top:8px">
          <select id="propose-book-select">${proposableBooks.map((book) => `<option value="${book.id}">${escapeHtml(book.title)}</option>`).join("")}</select>
          <button class="secondary-button" type="submit">Propose</button>
        </div>
      </form>`;

  const newBookForm = showResults
    ? ""
    : `<form id="propose-new-book-form" class="dash-scan-form" style="margin-top:12px">
        <label for="propose-new-book-title">Suggest a book we don't have yet</label>
        <div style="display:flex;gap:8px;margin-top:8px;flex-wrap:wrap">
          <input id="propose-new-book-title" type="text" placeholder="Title" required />
          <input id="propose-new-book-author" type="text" placeholder="Author" required />
          <button class="secondary-button" type="submit">Propose</button>
        </div>
      </form>`;

  const pendingCopy = myPending.length
    ? `<p class="muted" style="margin-top:14px">Awaiting facilitator approval: ${myPending.map((c) => escapeHtml(c.book.title)).join(", ")}</p>`
    : "";

  content.innerHTML = `<div class="user-list">${approved
    .map((candidate) =>
      renderVotingCandidate(candidate, {
        showResults,
        myVoteId: round.my_vote_candidate_id,
        isWinner: showResults && round.winning_book && candidate.book.id === round.winning_book.id,
      }),
    )
    .join("")}</div>${proposeForm}${newBookForm}${pendingCopy}`;
  renderActionCenter();
};

const loadVoting = async () => {
  try {
    const round = await request("/participant/voting-round");
    renderVoting(round);
  } catch (error) {
    if (error.status === 404) renderVoting(null);
    else toast(error.message);
  }
};

document.addEventListener("submit", async (event) => {
  if (event.target.id !== "propose-candidate-form") return;
  event.preventDefault();
  const bookId = Number($("#propose-book-select").value);
  try {
    await request("/participant/voting-round/candidates", {
      method: "POST",
      body: JSON.stringify({ book_id: bookId }),
    });
    toast("Proposed — waiting on facilitator approval.");
    await loadVoting();
    await loadActivity();
  } catch (error) {
    toast(error.message);
  }
});

document.addEventListener("submit", async (event) => {
  if (event.target.id !== "propose-new-book-form") return;
  event.preventDefault();
  const title = $("#propose-new-book-title").value.trim();
  const author = $("#propose-new-book-author").value.trim();
  if (!title || !author) return;
  try {
    await request("/participant/voting-round/candidates/new-book", {
      method: "POST",
      body: JSON.stringify({ title, author }),
    });
    toast("Proposed — waiting on facilitator approval.");
    await loadVoting();
    await loadActivity();
  } catch (error) {
    toast(error.message);
  }
});

$("#voting-content").addEventListener("click", async (event) => {
  const button = event.target.closest("[data-vote-candidate]");
  if (!button) return;
  try {
    const round = await request("/participant/voting-round/vote", {
      method: "PUT",
      body: JSON.stringify({ candidate_id: Number(button.dataset.voteCandidate) }),
    });
    renderVoting(round);
    toast("Vote saved.");
    await loadActivity();
  } catch (error) {
    toast(error.message);
  }
});

const renderDatePollOption = (option, { showResults, myVoteId, isWinner }) => {
  const isMine = option.id === myVoteId;
  const countCopy = showResults && option.vote_count != null ? ` · ${option.vote_count} vote${option.vote_count === 1 ? "" : "s"}` : "";
  return `<article class="user-card" data-option-id="${option.id}">
    <div>
      <h3>${escapeHtml(formatDate(option.option_date))}${isWinner ? " 🏆" : ""}</h3>
      <p class="user-meta">${countCopy || " "}</p>
    </div>
    <div class="user-actions">
      ${
        showResults
          ? ""
          : `<button class="${isMine ? "primary-button" : "secondary-button"}" data-vote-option="${option.id}">${isMine ? "Your vote" : "Vote"}</button>`
      }
    </div>
  </article>`;
};

const renderDatePoll = (poll) => {
  participantState.datePoll = poll;
  const content = $("#date-poll-content");
  if (!poll) {
    $("#date-poll-heading").textContent = "Meeting date";
    content.innerHTML = '<p class="muted">No date poll is open right now.</p>';
    renderActionCenter();
    return;
  }
  const showResults = poll.status === "closed";
  $("#date-poll-heading").textContent = showResults ? "Results" : "Cast your vote";
  content.innerHTML = `<div class="user-list">${poll.options
    .map((option) =>
      renderDatePollOption(option, {
        showResults,
        myVoteId: poll.my_vote_option_id,
        isWinner: showResults && poll.winning_date === option.option_date,
      }),
    )
    .join("")}</div>`;
  renderActionCenter();
};

const loadDatePoll = async () => {
  try {
    const poll = await request("/participant/date-poll");
    renderDatePoll(poll);
  } catch (error) {
    if (error.status === 404) renderDatePoll(null);
    else toast(error.message);
  }
};

$("#date-poll-content").addEventListener("click", async (event) => {
  const button = event.target.closest("[data-vote-option]");
  if (!button) return;
  try {
    const poll = await request("/participant/date-poll/vote", {
      method: "PUT",
      body: JSON.stringify({ option_id: Number(button.dataset.voteOption) }),
    });
    renderDatePoll(poll);
    toast("Vote saved.");
    await loadActivity();
  } catch (error) {
    toast(error.message);
  }
});

const ratingsState = { participantId: null, pendingStars: {}, dataByBook: {}, mineByBook: {} };

const renderBookRatingCard = (book, ratingsData, status) => {
  const mine = ratingsData.ratings.find((entry) => entry.participant_id === ratingsState.participantId);
  const statusCopy = { current: "Current", up_next: "Coming up", previously_read: "Previously read" }[status];
  const statusClass = { current: "current", up_next: "up-next", previously_read: "previous" }[status];
  return `<article class="participant-book-card" data-open-book="${book.id}" data-book-id="${book.id}" tabindex="0" role="button" aria-label="Open ${escapeHtml(book.title)}"><div class="participant-book-cover-wrap"><img src="${escapeHtml(book.cover_image_url || "/static/assets/library-tools-logo-classic.svg?v=1")}" alt="" loading="lazy" /></div><div class="participant-book-card-copy"><span class="book-status ${statusClass}">${statusCopy}</span><h3>${escapeHtml(book.title)}</h3><p>${escapeHtml(book.author)}</p>${status === "current" && book.description ? `<p class="participant-book-card-description">${escapeHtml(book.description)}</p>` : ""}<div class="participant-book-card-meta">${book.page_count ? `<span>${book.page_count} pages</span>` : ""}${ratingsData.count ? `<span class="club-rating">${ratingsData.average}★ club</span>` : "<span>Not rated</span>"}${mine ? `<span class="reader-rating">Your rating ${mine.rating}★</span>` : ""}</div></div><span class="book-open-cue">Open book <svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m9 18 6-6-6-6" /></svg></span></article>`;
};

const journeyFeatureBookMarkup = (book, label, className) => {
  if (!book) return `<div class="journey-book-empty"><span aria-hidden="true"><svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14" /><path d="M12 5v14" /></svg></span><div><strong>${escapeHtml(label)}</strong><p>The facilitator’s next selection will appear here.</p></div></div>`;
  const ratings = ratingsState.dataByBook[book.id];
  return `<article class="journey-feature-book ${className}" data-open-book="${book.id}" role="button" tabindex="0" aria-label="Open ${escapeHtml(book.title)}"><img src="${escapeHtml(book.cover_image_url || "/static/assets/library-tools-logo-classic.svg?v=1")}" alt="" /><div><span>${escapeHtml(label)}</span><h2>${escapeHtml(book.title)}</h2><p>${escapeHtml(book.author)}</p><small>${book.page_count ? `${book.page_count} pages` : "Page count unavailable"}${ratings?.count ? ` · ${ratings.average}★ from the club` : " · Not rated yet"}</small></div><b aria-hidden="true"><svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m9 18 6-6-6-6" /></svg></b></article>`;
};

const renderBooksJourneyOverview = () => {
  const current = participantState.library.current[0];
  const next = participantState.library.up_next[0];
  const completed = participantState.library.previously_read.length;
  const total = completed + participantState.library.current.length + participantState.library.up_next.length;
  const overview = $("#books-journey-overview");
  const suggestion = $(".book-suggestion-section");
  overview.innerHTML = `<div class="journey-overview-heading"><div><p class="eyebrow">Where the club is now</p><h2>${completed ? `${completed} finished ${completed === 1 ? "book" : "books"}, with more ahead` : "The first chapter starts here"}</h2></div><div class="journey-counts"><span><strong>${total}</strong> on the shared shelf</span><span><strong>${completed}</strong> completed together</span></div></div><div class="journey-feature-grid">${journeyFeatureBookMarkup(current, "Reading now", "is-current")}${journeyFeatureBookMarkup(next, "Coming up", "is-next")}</div>`;
  if (suggestion) overview.querySelector(".journey-feature-grid").before(suggestion);
};

const renderJourneyShelf = (visible) => {
  const chapters = [
    ["current", "Reading now", "The book bringing the club together today"],
    ["up_next", "Coming up", "The next chapters waiting on the shared shelf"],
    ["previously_read", "Previously read", "Finished books that became part of the club’s story"],
  ];
  return `<div class="journey-shelf-groups">${chapters.map(([status, title, description], chapterIndex) => {
    const items = visible.filter((item) => item.status === status);
    if (!items.length) return "";
    return `<section class="journey-shelf-group ${status}"><header><div><i>Chapter 0${chapterIndex + 1}</i><span>${escapeHtml(title)}</span><p>${escapeHtml(description)}</p></div><b>${items.length} ${items.length === 1 ? "book" : "books"}</b></header><div class="participant-book-grid">${items.map(({ book }) => renderBookRatingCard(book, ratingsState.dataByBook[book.id], status)).join("")}</div></section>`;
  }).join("")}</div>`;
};

const loadRatings = async () => {
  const list = $("#ratings-list");
  const groups = [
    ["current", participantState.library.current],
    ["up_next", participantState.library.up_next],
    ["previously_read", participantState.library.previously_read],
  ];
  const query = $("#library-search").value.trim().toLocaleLowerCase();
  const statusFilter = $("#library-status-filter").value;
  const sort = $("#library-sort").value;
  const books = [...new Map(groups.flatMap(([, items]) => items).map((book) => [book.id, book])).values()];
  if (!books.length) {
    list.innerHTML = '<p class="muted">No books have been scheduled or completed yet.</p>';
    renderBooksJourneyOverview();
    return;
  }
  const missing = books.filter((book) => !ratingsState.dataByBook[book.id]);
  const loaded = await Promise.all(missing.map((book) => request(`/participant/books/${book.id}/ratings`)));
  missing.forEach((book, index) => { ratingsState.dataByBook[book.id] = loaded[index]; });
  ratingsState.mineByBook = Object.fromEntries(books.map((book) => [book.id, ratingsState.dataByBook[book.id].ratings.find((entry) => entry.participant_id === ratingsState.participantId) || null]));
  let visible = groups.flatMap(([status, items]) => items.map((book) => ({ book, status })));
  visible = visible.filter(({ book, status }) => (statusFilter === "all" || status === statusFilter) && (!query || `${book.title} ${book.author}`.toLocaleLowerCase().includes(query)));
  if (sort === "title") visible.sort((left, right) => left.book.title.localeCompare(right.book.title));
  if (sort === "rating") visible.sort((left, right) => (ratingsState.dataByBook[right.book.id].average || 0) - (ratingsState.dataByBook[left.book.id].average || 0));
  list.innerHTML = visible.length ? (sort === "journey" ? renderJourneyShelf(visible) : `<div class="participant-book-grid flat-book-grid">${visible.map(({ book, status }) => renderBookRatingCard(book, ratingsState.dataByBook[book.id], status)).join("")}</div>`) : '<p class="muted">No books match your search.</p>';
  renderBooksJourneyOverview();
  renderPostMeeting();
  renderActionCenter();
};

$("#library-search").addEventListener("input", () => loadRatings().catch((error) => toast(error.message)));
$("#library-status-filter").addEventListener("change", () => loadRatings().catch((error) => toast(error.message)));
$("#library-sort").addEventListener("change", () => loadRatings().catch((error) => toast(error.message)));

const bookSuggestionState = { results: [], selected: null, controller: null, submitted: null, searchTimer: null };

const setBookSuggestionOpen = (open, { focus = false } = {}) => {
  const section = $(".book-suggestion-section");
  section.classList.toggle("is-collapsed", !open);
  section.classList.toggle("is-open", open);
  $("#suggestion-workspace").hidden = !open;
  $("#suggestion-launch").setAttribute("aria-expanded", String(open));
  $("[data-suggestion-launch-label]").textContent = open ? "Close" : "Open";
  if (focus) $("#google-book-query").focus();
};

$("#suggestion-launch").addEventListener("click", () => {
  const open = $("#suggestion-launch").getAttribute("aria-expanded") !== "true";
  setBookSuggestionOpen(open, { focus: open });
});

const googleBookCover = (book) => String(book.volumeInfo?.imageLinks?.thumbnail || "/static/assets/library-tools-logo-classic.svg?v=1").replace(/^http:/, "https:");

const renderGoogleBookResults = () => {
  const results = $("#google-book-results");
  results.innerHTML = bookSuggestionState.results.map((book, index) => {
    const info = book.volumeInfo || {};
    const selected = bookSuggestionState.selected?.id === book.id;
    return `<button class="google-book-result${selected ? " is-selected" : ""}" type="button" role="option" aria-selected="${selected}" data-google-book-index="${index}"><img src="${escapeHtml(googleBookCover(book))}" alt="" loading="lazy" /><span><strong>${escapeHtml(info.title || "Untitled")}</strong><small>${escapeHtml((info.authors || ["Unknown author"]).join(", "))}</small><b>${escapeHtml(info.publishedDate?.slice(0, 4) || "Publication year unavailable")}</b></span><i aria-hidden="true"><svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m9 18 6-6-6-6" /></svg></i></button>`;
  }).join("");
  const expanded = bookSuggestionState.results.length > 0 && !bookSuggestionState.selected;
  results.hidden = !expanded;
  $("#google-book-query").setAttribute("aria-expanded", String(expanded));
};

const renderSuggestionPreview = () => {
  const preview = $("#suggestion-preview");
  if (bookSuggestionState.submitted) {
    const suggestion = bookSuggestionState.submitted;
    preview.hidden = false;
    preview.innerHTML = `<div class="suggestion-sent"><span aria-hidden="true"><svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5" /></svg></span><div><p class="eyebrow">Suggestion sent</p><h3>${escapeHtml(suggestion.title)}</h3><p>Your facilitator can now review your suggestion and comments. You’ll see it in the club library if they add it.</p></div><button class="secondary-button" type="button" data-suggest-another>Suggest another book</button></div>`;
    return;
  }
  const book = bookSuggestionState.selected;
  if (!book) { preview.hidden = true; return; }
  const info = book.volumeInfo || {};
  preview.hidden = false;
  preview.innerHTML = `<div class="suggestion-preview-book"><img src="${escapeHtml(googleBookCover(book))}" alt="" /><div><p class="eyebrow">Selected book</p><h3>${escapeHtml(info.title || "Untitled")}</h3><p>${escapeHtml((info.authors || ["Unknown author"]).join(", "))}${info.publishedDate ? ` · ${escapeHtml(info.publishedDate.slice(0, 4))}` : ""}</p></div><button class="quiet-button" type="button" data-change-suggestion-book>Change book</button></div><form class="suggestion-destination" id="book-suggestion-submit-form"><div class="suggestion-comment-heading"><strong>Why are you suggesting this book?</strong><span>Optional</span><p>Share what could make it an interesting club read. Your note will only be seen by the facilitator.</p></div><label class="sr-only" for="book-suggestion-comments">Comments about this suggestion</label><textarea id="book-suggestion-comments" name="comments" rows="4" maxlength="2000" placeholder="For example: themes worth discussing, why members might enjoy it, or any content notes…"></textarea><div class="suggestion-submit-row"><small><span data-comment-count>0</span>/2,000 characters</small><button type="submit">Send to facilitator</button></div></form>`;
};

const searchBookSuggestions = async (query) => {
  bookSuggestionState.controller?.abort();
  bookSuggestionState.controller = new AbortController();
  $("#google-book-status").textContent = "Searching Google Books…";
  try {
    const result = await request("/participant/book-suggestions/search", {
      method: "POST",
      signal: bookSuggestionState.controller.signal,
      body: JSON.stringify({ query }),
    });
    bookSuggestionState.results = (result.results || []).map((book) => ({
      id: book.external_id,
      volumeInfo: {
        title: book.title,
        authors: book.author ? book.author.split(";").map((author) => author.trim()).filter(Boolean) : [],
        publishedDate: book.publication_date,
        description: book.description,
        imageLinks: book.cover_image_url ? { thumbnail: book.cover_image_url } : undefined,
        industryIdentifiers: book.isbn ? [{ type: book.isbn.length === 13 ? "ISBN_13" : "ISBN_10", identifier: book.isbn }] : [],
        pageCount: book.page_count,
      },
    }));
    bookSuggestionState.selected = null;
    bookSuggestionState.submitted = null;
    renderSuggestionPreview();
    renderGoogleBookResults();
    $("#google-book-status").textContent = bookSuggestionState.results.length ? `Choose from ${bookSuggestionState.results.length} matching books.` : "No matching books found. Try a title, author, or ISBN.";
  } catch (error) {
    if (error.name === "AbortError") return;
    bookSuggestionState.results = [];
    bookSuggestionState.selected = null;
    bookSuggestionState.submitted = null;
    renderSuggestionPreview();
    renderGoogleBookResults();
    $("#google-book-status").textContent = error.message;
  }
};

$("#google-book-search-form").addEventListener("submit", (event) => {
  event.preventDefault();
  clearTimeout(bookSuggestionState.searchTimer);
  const query = $("#google-book-query").value.trim();
  if (query.length >= 2) searchBookSuggestions(query);
});

$("#google-book-query").addEventListener("input", (event) => {
  clearTimeout(bookSuggestionState.searchTimer);
  bookSuggestionState.controller?.abort();
  const query = event.target.value.trim();
  bookSuggestionState.selected = null;
  bookSuggestionState.submitted = null;
  renderSuggestionPreview();
  if (query.length < 2) {
    bookSuggestionState.results = [];
    renderGoogleBookResults();
    $("#google-book-status").textContent = query ? "Keep typing to search." : "Start typing to search.";
    return;
  }
  $("#google-book-status").textContent = "Waiting for you to finish typing…";
  bookSuggestionState.searchTimer = setTimeout(() => searchBookSuggestions(query), 350);
});

$("#google-book-results").addEventListener("click", (event) => {
  const result = event.target.closest("[data-google-book-index]");
  if (!result) return;
  bookSuggestionState.selected = bookSuggestionState.results[Number(result.dataset.googleBookIndex)] || null;
  bookSuggestionState.submitted = null;
  const info = bookSuggestionState.selected?.volumeInfo || {};
  $("#google-book-query").value = [info.title, (info.authors || [])[0]].filter(Boolean).join(" — ");
  renderGoogleBookResults();
  renderSuggestionPreview();
  $("#google-book-status").textContent = `${info.title || "Book"} selected. Add an optional comment below.`;
});

$("#google-book-query").addEventListener("keydown", (event) => {
  if (event.key !== "Escape") return;
  $("#google-book-results").hidden = true;
  event.currentTarget.setAttribute("aria-expanded", "false");
});

$("#google-book-query").addEventListener("focus", () => {
  if (!bookSuggestionState.results.length || bookSuggestionState.selected) return;
  $("#google-book-results").hidden = false;
  $("#google-book-query").setAttribute("aria-expanded", "true");
});

document.addEventListener("click", (event) => {
  if (event.target.closest(".suggestion-search-control")) return;
  $("#google-book-results").hidden = true;
  $("#google-book-query").setAttribute("aria-expanded", "false");
});

$("#suggestion-preview").addEventListener("input", (event) => {
  if (event.target.name !== "comments") return;
  const count = event.target.form?.querySelector("[data-comment-count]");
  if (count) count.textContent = event.target.value.length.toLocaleString();
});

$("#suggestion-preview").addEventListener("click", (event) => {
  if (!event.target.closest("[data-suggest-another], [data-change-suggestion-book]")) return;
  event.stopPropagation();
  bookSuggestionState.submitted = null;
  bookSuggestionState.selected = null;
  renderGoogleBookResults();
  renderSuggestionPreview();
  $("#google-book-status").textContent = "Choose another match below, or type a new search.";
  $("#google-book-query").focus();
  $("#google-book-query").select();
});

$("#suggestion-preview").addEventListener("submit", async (event) => {
  if (event.target.id !== "book-suggestion-submit-form") return;
  event.preventDefault();
  const book = bookSuggestionState.selected;
  if (!book) return;
  const info = book.volumeInfo || {};
  const button = event.target.querySelector("button[type=submit]");
  button.disabled = true;
  button.textContent = "Sending…";
  const published = String(info.publishedDate || "");
  const publicationDate = /^\d{4}-\d{2}-\d{2}$/.test(published)
    ? published
    : /^\d{4}/.test(published) ? `${published.slice(0, 4)}-01-01` : null;
  const identifiers = info.industryIdentifiers || [];
  const isbn = identifiers.find((item) => item.type === "ISBN_13")?.identifier
    || identifiers.find((item) => item.type === "ISBN_10")?.identifier
    || null;
  try {
    const suggestion = await request("/participant/book-suggestions", {
      method: "POST",
      body: JSON.stringify({
        google_books_id: book.id || null,
        title: info.title || "Untitled",
        author: (info.authors || ["Unknown author"]).join(", "),
        description: info.description || null,
        cover_image_url: info.imageLinks?.thumbnail ? googleBookCover(book) : null,
        publication_date: publicationDate,
        isbn,
        page_count: Number(info.pageCount) > 0 ? Number(info.pageCount) : null,
        comments: event.target.elements.comments.value.trim() || null,
      }),
    });
    bookSuggestionState.submitted = suggestion;
    bookSuggestionState.selected = null;
    renderGoogleBookResults();
    renderSuggestionPreview();
    await Promise.all([loadStats(), loadActivity()]);
    toast("Suggestion sent to your facilitator.");
  } catch (error) {
    button.disabled = false;
    button.textContent = "Send suggestion";
    toast(error.message);
  }
});

$("#ratings-list").addEventListener("click", (event) => {
  const star = event.target.closest("[data-star]");
  if (star) {
    ratingsState.pendingStars[star.dataset.bookId] = Number(star.dataset.star);
    const row = star.closest(".star-row");
    [...row.children].forEach((button) => {
      button.classList.toggle("is-filled", Number(button.dataset.star) <= Number(star.dataset.star));
    });
  }
});

$("#ratings-list").addEventListener("click", async (event) => {
  const button = event.target.closest("[data-save-rating]");
  if (!button) return;
  const bookId = button.dataset.saveRating;
  const card = button.closest(".rating-card");
  const stars = ratingsState.pendingStars[bookId]
    ?? card.querySelectorAll(".star-button.is-filled").length;
  if (!stars) {
    toast("Choose a star rating first.");
    return;
  }
  const reviewText = card.querySelector(".rating-review").value.trim() || null;
  try {
    await request(`/participant/books/${bookId}/rating`, {
      method: "PUT",
      body: JSON.stringify({ rating: stars, review_text: reviewText }),
    });
    delete ratingsState.pendingStars[bookId];
    delete ratingsState.dataByBook[bookId];
    toast("Rating saved.");
    await loadRatings();
    await loadActivity();
  } catch (error) {
    toast(error.message);
  }
});

const renderPostMeeting = () => {
  const section = $("#post-meeting-section");
  const completed = participantState.latestCompletedMeeting;
  if (!completed) { section.hidden = true; return; }
  const book = completed.meeting.book;
  const mine = ratingsState.mineByBook[book.id];
  section.hidden = false;
  $("#post-meeting-heading").textContent = mine ? `Thanks for sharing your take on ${book.title}` : `What did you think of ${book.title}?`;
  $("#post-meeting-copy").textContent = mine ? `You rated it ${mine.rating} star${mine.rating === 1 ? "" : "s"}. You can update your rating or join the conversation anytime.` : `Capture a quick rating or reflection while the conversation is still fresh.`;
  $("#post-meeting-actions").innerHTML = `<button class="primary-button" type="button" data-open-book="${book.id}">${mine ? "Update my review" : "Rate this book"}</button><button class="secondary-button" type="button" data-open-book="${book.id}">Open discussion</button>`;
};

$("#logout").addEventListener("click", async () => {
  await request("/participant/auth/logout", { method: "POST" });
  location.href = "/";
});

$("#resend-verification").addEventListener("click", async () => {
  try {
    const result = await request("/participant/auth/email-verification/request", { method: "POST" });
    const note = $("#verification-delivery-note");
    note.hidden = false;
    note.textContent = result.delivery_configured
      ? "A fresh verification link was sent."
      : "A fresh link is ready, but email delivery has not been connected yet for this club.";
  } catch (error) {
    toast(error.message);
  }
});

const renderActivity = (activity) => {
  const stats = [
    [activity.attended_meetings_count, "meetings attended"],
    [activity.ratings_count, "books rated"],
    [activity.book_votes_count + activity.date_votes_count, "votes cast"],
    [activity.proposals_count, "books proposed"],
  ];
  $("#activity-stats").innerHTML = stats.map(([count, label]) => `<div class="activity-stat"><strong>${count}</strong><span>${label}</span></div>`).join("");
};

const loadActivity = async () => renderActivity(await request("/participant/activity"));

const statCardsMarkup = (items, className = "") => `<div class="portal-stat-grid${className ? ` ${escapeHtml(className)}` : ""}">${items.map(([value, label, icon]) => `<article class="portal-stat-card">${icon ? `<i aria-hidden="true">${icon}</i>` : ""}<div class="portal-stat-copy"><strong>${escapeHtml(String(value))}</strong><span>${escapeHtml(label)}</span></div></article>`).join("")}</div>`;

const statBarsMarkup = (items, emptyCopy) => {
  if (!items.length) return `<p class="muted">${escapeHtml(emptyCopy)}</p>`;
  const maximum = Math.max(...items.map((item) => item.value), 1);
  return `<div class="stat-bar-list">${items.map((item) => `<div class="stat-bar-row"><strong>${escapeHtml(item.label)}</strong><div class="stat-bar-track"><span style="width:${Math.round((item.value / maximum) * 100)}%"></span></div><b>${item.value}</b></div>`).join("")}</div>`;
};

const personalActivityMarkup = (items) => items.map((item) => `<article><small>${escapeHtml(formatTimestamp(item.occurred_at))}</small><p><strong>${escapeHtml(item.label)}</strong>${item.detail ? `<br><small>${escapeHtml(item.detail)}</small>` : ""}</p></article>`).join("");

const renderPersonalStats = (stats) => {
  participantState.personalStats = stats;
  $("#personal-stats-content").innerHTML = `${statCardsMarkup([
    [stats.meetings_attended, "Meetings attended", '<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M8 2v3" /><path d="M16 2v3" /><rect x="3" y="3" width="18" height="18" rx="2" /><path d="M3 9h18" /><path d="M8 13h.01" /><path d="M12 13h.01" /><path d="M16 13h.01" /><path d="M8 17h.01" /><path d="M12 17h.01" /><path d="M16 17h.01" /></svg>'],
    [stats.books_read, "Books read", '<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 5v16" /><path d="M20.001 19A2 2 0 0022 17V5a2 2 0 00-1.999-2L16 3.002A5 5 0 0012 5a5 5 0 00-4-2H4a2 2 0 00-2 2v12a2 2 0 001.999 2H8a5 5 0 014 2 5 5 0 014-2z" /></svg>'],
    [stats.pages_read.toLocaleString(), "Pages read", '<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 22a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h8a2.4 2.4 0 0 1 1.704.706l3.588 3.588A2.4 2.4 0 0 1 20 8v12a2 2 0 0 1-2 2z" /><path d="M14 2v5a1 1 0 0 0 1 1h5" /><path d="M10 9H8" /><path d="M16 13H8" /><path d="M16 17H8" /></svg>'],
    [stats.books_rated, "Books rated", '<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11.525 2.295a.53.53 0 0 1 .95 0l2.31 4.679a2.123 2.123 0 0 0 1.595 1.16l5.166.756a.53.53 0 0 1 .294.904l-3.736 3.638a2.123 2.123 0 0 0-.611 1.878l.882 5.14a.53.53 0 0 1-.771.56l-4.618-2.428a2.122 2.122 0 0 0-1.973 0L6.396 21.01a.53.53 0 0 1-.77-.56l.881-5.139a2.122 2.122 0 0 0-.611-1.879L2.16 9.795a.53.53 0 0 1 .294-.906l5.165-.755a2.122 2.122 0 0 0 1.597-1.16z" /></svg>'],
  ], "personal-stat-overview")}<div class="stats-layout personal-stats-layout"><section class="stats-panel personal-taste-panel"><p class="eyebrow">Your taste</p><h2>Favourite genres</h2>${statBarsMarkup(stats.favourite_genres, "Attend a completed meeting to begin your genre portrait.")}</section><section class="stats-panel personal-ratings-panel"><p class="eyebrow">Your ratings</p><h2>${stats.average_rating == null ? "No ratings yet" : `${stats.average_rating}★ average`}</h2>${statBarsMarkup(stats.rating_distribution, "Your rating pattern will appear after you rate a book.")}</section><section class="stats-panel personal-shelf-panel"><p class="eyebrow">Reading now</p><h2>Your shelf</h2>${statCardsMarkup([[stats.finished_books, "Marked finished"], [stats.in_progress_books, "In progress"], [stats.votes_cast, "Votes cast"], [stats.proposals_made, "Books proposed"]])}</section><section class="stats-panel personal-activity-panel"><p class="eyebrow">Recently</p><h2>Your activity</h2><div class="stats-timeline">${stats.recent.length ? personalActivityMarkup(stats.recent.slice(0, 4)) : '<p class="muted">Ratings, votes, proposals, and progress updates will appear here.</p>'}</div>${stats.recent.length > 4 ? `<button class="activity-view-all" id="view-all-personal-activity" type="button">View all activity <span>${stats.recent.length}</span></button>` : ""}</section></div>`;
};

$("#personal-stats-content").addEventListener("click", (event) => {
  if (!event.target.closest("#view-all-personal-activity")) return;
  const activity = participantState.personalStats?.recent || [];
  $("#personal-activity-dialog-list").innerHTML = personalActivityMarkup(activity);
  $("#personal-activity-dialog-count").textContent = `${activity.length} ${activity.length === 1 ? "update" : "updates"}`;
  $("#personal-activity-dialog").showModal();
});

$("#close-personal-activity-dialog").addEventListener("click", () => $("#personal-activity-dialog").close());

const clubPersonalityCopy = (stats) => {
  const leadingGenre = stats.favourite_genres[0]?.label;
  const leadingLength = [...stats.page_length_mix].sort((a, b) => b.value - a.value)[0]?.label;
  const parts = [];
  if (leadingGenre) parts.push(`${leadingGenre} leads the club’s shared shelf`);
  if (leadingLength) parts.push(`${leadingLength.toLowerCase()} is the most common book length`);
  if (stats.average_rating != null) parts.push(`members give their reads ${stats.average_rating} stars on average`);
  if (!parts.length) return "As the club reads and reacts together, its shared personality will take shape here.";
  return `${parts.map((part) => capitalizeFirst(part)).join(". ")}.`;
};

const clubConversationBookMarkup = (book, label) => {
  if (!book) return `<article class="conversation-insight is-empty"><span>${escapeHtml(label)}</span><p>More reader activity will reveal this insight.</p></article>`;
  return `<article class="conversation-insight" data-open-book="${book.book_id}" role="button" tabindex="0"><img src="${escapeHtml(book.cover_image_url || "/static/assets/library-tools-logo-classic.svg?v=1")}" alt="" /><div><span>${escapeHtml(label)}</span><strong>${escapeHtml(book.title)}</strong><small>${escapeHtml(book.author)}</small><b>${escapeHtml(book.detail)}</b></div><svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m9 18 6-6-6-6" /></svg></article>`;
};

const clubConversationPulseMarkup = (stats) => {
  const highlight = stats.conversation_highlight;
  return `<section class="stats-panel club-conversation-pulse"><div class="club-conversation-heading"><div><p class="eyebrow">Beyond the ratings</p><h2>Club conversation pulse</h2><p>Where readers are gathering, reacting, and seeing books differently.</p></div><div class="conversation-totals"><span><strong>${stats.conversation_total}</strong> comments</span><span><strong>${stats.conversation_participants}</strong> readers joining in</span></div></div><div class="conversation-pulse-grid"><div class="conversation-insights">${clubConversationBookMarkup(stats.most_discussed_book, "Most discussed")}${clubConversationBookMarkup(stats.most_divisive_book, "Most debated")}</div>${highlight ? `<article class="conversation-highlight" data-open-book="${highlight.book_id}" role="button" tabindex="0"><div class="conversation-quote-mark" aria-hidden="true">“</div><p>${escapeHtml(highlight.body)}</p><footer><span><strong>${escapeHtml(highlight.author_name)}</strong> on ${escapeHtml(highlight.book_title)}</span><small>${escapeHtml(formatTimestamp(highlight.created_at))}</small></footer></article>` : '<article class="conversation-highlight is-empty"><div class="conversation-quote-mark" aria-hidden="true">“</div><p>The next thoughtful comment will become the club’s conversation highlight.</p><footer><span>Start a conversation from any book page.</span></footer></article>'}</div></section>`;
};

const renderClubStats = (stats) => {
  participantState.clubStats = stats;
  const highestRated = stats.top_rated_books[0];
  $("#club-stats-content").innerHTML = `<section class="club-personality-hero"><div class="club-personality-copy"><p class="eyebrow">Our reading personality</p><h2>${stats.books_completed ? `${stats.books_completed} books into the story` : "A story just beginning"}</h2><p>${escapeHtml(clubPersonalityCopy(stats))}</p>${highestRated ? `<p class="club-favourite-note"><span aria-hidden="true"><svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11.525 2.295a.53.53 0 0 1 .95 0l2.31 4.679a2.123 2.123 0 0 0 1.595 1.16l5.166.756a.53.53 0 0 1 .294.904l-3.736 3.638a2.123 2.123 0 0 0-.611 1.878l.882 5.14a.53.53 0 0 1-.771.56l-4.618-2.428a2.122 2.122 0 0 0-1.973 0L6.396 21.01a.53.53 0 0 1-.77-.56l.881-5.139a2.122 2.122 0 0 0-.611-1.879L2.16 9.795a.53.53 0 0 1 .294-.906l5.165-.755a2.122 2.122 0 0 0 1.597-1.16z" /></svg></span><strong>Reader favourite:</strong> ${escapeHtml(highestRated.title)}</p>` : ""}</div>${statCardsMarkup([
    [stats.active_members, "Active readers", '<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" /><path d="M16 3.128a4 4 0 0 1 0 7.744" /><path d="M22 21v-2a4 4 0 0 0-3-3.87" /><circle cx="9" cy="7" r="4" /></svg>'],
    [stats.books_completed, "Books completed", '<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 5v16" /><path d="M20.001 19A2 2 0 0022 17V5a2 2 0 00-1.999-2L16 3.002A5 5 0 0012 5a5 5 0 00-4-2H4a2 2 0 00-2 2v12a2 2 0 001.999 2H8a5 5 0 014 2 5 5 0 014-2z" /></svg>'],
    [stats.pages_read_together.toLocaleString(), "Pages read together", '<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 22a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h8a2.4 2.4 0 0 1 1.704.706l3.588 3.588A2.4 2.4 0 0 1 20 8v12a2 2 0 0 1-2 2z" /><path d="M14 2v5a1 1 0 0 0 1 1h5" /><path d="M10 9H8" /><path d="M16 13H8" /><path d="M16 17H8" /></svg>'],
    [stats.average_rating == null ? "—" : `${stats.average_rating}★`, `${stats.rating_count} shared ratings`, '<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11.525 2.295a.53.53 0 0 1 .95 0l2.31 4.679a2.123 2.123 0 0 0 1.595 1.16l5.166.756a.53.53 0 0 1 .294.904l-3.736 3.638a2.123 2.123 0 0 0-.611 1.878l.882 5.14a.53.53 0 0 1-.771.56l-4.618-2.428a2.122 2.122 0 0 0-1.973 0L6.396 21.01a.53.53 0 0 1-.77-.56l.881-5.139a2.122 2.122 0 0 0-.611-1.879L2.16 9.795a.53.53 0 0 1 .294-.906l5.165-.755a2.122 2.122 0 0 0 1.597-1.16z" /></svg>'],
  ], "club-story-overview")}</section><div class="club-profile-grid"><section class="stats-panel club-genre-panel"><p class="eyebrow">What we reach for</p><h2>Favourite territory</h2>${statBarsMarkup(stats.favourite_genres, "Genres have not been added to the club books yet.")}</section><section class="stats-panel club-length-panel"><p class="eyebrow">Our reading rhythm</p><h2>Book-length mix</h2>${statBarsMarkup(stats.page_length_mix, "Page counts have not been added yet.")}</section></div><section class="stats-panel club-favourites-panel"><div class="club-panel-heading"><div><p class="eyebrow">Reader favourites</p><h2>Books we loved together</h2></div><p>Shared ratings reveal the titles that stayed with the club.</p></div><div class="top-books-grid">${stats.top_rated_books.length ? stats.top_rated_books.map((book) => `<article class="top-book" data-open-book="${book.book_id}" role="button" tabindex="0"><img src="${escapeHtml(book.cover_image_url || "/static/assets/library-tools-logo-classic.svg?v=1")}" alt="" /><div><strong>${escapeHtml(book.title)}</strong><p>${escapeHtml(book.author)}</p><b>${book.average_rating}★ · ${book.rating_count} rating${book.rating_count === 1 ? "" : "s"}</b></div></article>`).join("") : '<p class="muted">Reader favourites will appear once members share their ratings.</p>'}</div></section>${clubConversationPulseMarkup(stats)}<div class="club-pulse-grid"><section class="stats-panel club-shelf-panel"><p class="eyebrow">The shared shelf</p><h2>${stats.shelf_total} books and counting</h2>${statBarsMarkup([{ label: "Completed", value: stats.shelf_completed }, { label: "Reading now", value: stats.shelf_current }, { label: "Coming up", value: stats.shelf_up_next }], "Books will appear as the facilitator builds the shelf.")}</section><section class="stats-panel club-reactions-panel"><p class="eyebrow">Shared reactions</p><h2>How ratings landed</h2>${statBarsMarkup(stats.rating_distribution, "The club has not rated a book yet.")}</section></div>`;
};

const loadStats = async () => {
  const [personal, club] = await Promise.all([
    request("/participant/stats/personal"),
    request("/participant/stats/club"),
  ]);
  renderPersonalStats(personal);
  renderClubStats(club);
};

const loadClubActivity = async () => {
  const activity = await request("/participant/club-activity");
  participantState.clubActivity = activity;
  const list = $("#activity-list");
  if (list) list.innerHTML = activity.length ? activity.map((item) => `<article class="feed-item">${avatarMarkup(item.actor)}<div><p><strong>${escapeHtml(item.actor.name)}</strong> ${item.kind === "rating" ? "rated" : item.kind === "progress" ? "updated their progress on" : "posted about"} <strong>${escapeHtml(item.book.title)}</strong>${item.detail ? ` · ${escapeHtml(item.detail)}` : ""}</p><small class="user-meta">${escapeHtml(formatTimestamp(item.created_at))}</small></div></article>`).join("") : '<p class="muted">Shared progress, ratings, and discussions will appear here.</p>';
};

const avatarMarkup = (profile) => profile.avatar_url
  ? `<span class="member-avatar"><img src="${escapeHtml(profile.avatar_url)}" alt="" /></span>`
  : `<span class="member-avatar">${escapeHtml(Array.from(profile.name || "?")[0]?.toLocaleUpperCase() || "?")}</span>`;

const renderDirectory = (members) => {
  $("#member-directory").innerHTML = members.length
    ? members.map((member) => `<article class="directory-card${member.is_self ? " is-self" : ""}"><div class="directory-card-top">${avatarMarkup(member)}<span>${member.is_self ? "Your profile" : "Club reader"}</span></div><div class="directory-card-copy"><h2>${escapeHtml(member.name)}</h2><p>${member.bio ? escapeHtml(member.bio) : "No introduction yet."}</p></div>${member.is_self ? '<small class="directory-self-note">Visible to your fellow club members</small>' : ""}</article>`).join("")
    : '<div class="directory-empty-state"><span aria-hidden="true"><svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" /><path d="M16 3.128a4 4 0 0 1 0 7.744" /><path d="M22 21v-2a4 4 0 0 0-3-3.87" /><circle cx="9" cy="7" r="4" /></svg></span><h2>The directory is ready for introductions</h2><p>Members appear here only after choosing to share a profile.</p></div>';
};

const loadDirectory = async () => renderDirectory(await request("/participant/members"));

const readingPaceCopy = (detail, progress) => {
  const { total, current, remaining, days, perDay, perWeek, meetingPassed } = readingPaceData(detail, progress);
  if (!total) return "Add a page count to this book to calculate a reading pace.";
  if (!detail.meeting_date) return `${Math.max(0, total - current)} pages remaining. Schedule a meeting to calculate a pace.`;
  if (!remaining) return "You’ve reached the end — nicely done.";
  if (meetingPassed) return `${remaining} pages remaining. The club meeting date has passed, so there’s no active pace target.`;
  return `${remaining} pages to go · ${perDay} per day or ${perWeek} per week to finish on time.`;
};

const readingPaceData = (detail, progress) => {
  const total = Number(detail.book.page_count || 0);
  const current = Math.min(total || Infinity, Math.max(0, Number(progress?.current_page || 0)));
  const remaining = Math.max(0, total - current);
  const percent = total ? Math.round((current / total) * 100) : 0;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const target = detail.meeting_date ? new Date(`${detail.meeting_date}T00:00:00`) : null;
  const meetingPassed = Boolean(target && target < today);
  const days = target && !meetingPassed ? Math.max(1, Math.ceil((target - today) / 86400000)) : null;
  return {
    total, current, remaining, percent, days, meetingPassed,
    perDay: days ? Math.ceil(remaining / days) : null,
    perWeek: days ? Math.ceil((remaining * 7) / days) : null,
  };
};

const readingProgressMarkup = (detail, progress) => {
  const pace = readingPaceData(detail, progress);
  const status = progress.status || "not_started";
  const statusOptions = [["not_started", "Not started"], ["reading", "Reading"], ["finished", "Finished"]];
  const pageMax = pace.total || 100;
  const sharedMarkup = detail.shared_progress.length
    ? detail.shared_progress.map((item) => {
      const memberPage = Number(item.current_page || 0);
      const memberPercent = pace.total ? Math.min(100, Math.round((memberPage / pace.total) * 100)) : 0;
      return `<article class="shared-reader-card">${avatarMarkup(item.member)}<div class="shared-reader-copy"><div><strong>${escapeHtml(item.member.name)}</strong><span>${escapeHtml(progressLabels[item.status] || item.status)}${item.current_page != null ? ` · page ${item.current_page}` : ""}</span></div><div class="shared-reader-track" aria-label="${memberPercent}% complete"><span style="width:${memberPercent}%"></span></div></div></article>`;
    }).join("")
    : '<div class="shared-progress-empty"><span aria-hidden="true"><svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" /><path d="M16 3.128a4 4 0 0 1 0 7.744" /><path d="M22 21v-2a4 4 0 0 0-3-3.87" /><circle cx="9" cy="7" r="4" /></svg></span><p><strong>Your club can read alongside you.</strong><br />Shared progress appears here without revealing notes or private activity.</p></div>';
  return `<div class="progress-calm-layout progress-experience"><form class="progress-form progress-calculator" id="detail-progress-form"><fieldset class="reading-status-picker"><legend>Reading status</legend><div>${statusOptions.map(([value, label]) => `<label><input type="radio" name="status" value="${value}"${status === value ? " checked" : ""} /><span>${label}</span></label>`).join("")}</div></fieldset><div class="progress-visual"><div class="progress-ring" data-progress-ring style="--progress:${pace.percent * 3.6}deg" role="img" aria-label="${pace.percent}% complete"><div><strong data-progress-percent>${pace.percent}%</strong><span>complete</span></div></div><div class="page-position"><div class="page-position-heading"><div><span>Current page</span><strong><output data-current-page>${pace.current}</output> <small>/ ${pace.total || "—"}</small></strong></div><label>Exact page<input name="current_page" type="number" min="0" max="${pageMax}" value="${pace.current}"${pace.total ? "" : " disabled"} /></label></div><input class="page-range" data-page-range type="range" min="0" max="${pageMax}" value="${pace.current}" step="1" style="--range-progress:${pace.percent}%" aria-label="Current page"${pace.total ? "" : " disabled"} /><div class="page-range-labels"><span>Beginning</span><span>${pace.total ? `Page ${pace.total}` : "Page count needed"}</span></div></div></div><div class="pace-dashboard"><article><span>Pages left</span><strong data-pages-remaining>${pace.total ? pace.remaining : "—"}</strong></article><article><span>Days left</span><strong data-days-remaining>${pace.days ?? "—"}</strong></article><article><span>Daily pace</span><strong><b data-pages-daily>${pace.perDay ?? "—"}</b><small> pages</small></strong></article><article><span>Weekly pace</span><strong><b data-pages-weekly>${pace.perWeek ?? "—"}</b><small> pages</small></strong></article></div><p class="pace-guidance" id="pace-result">${escapeHtml(readingPaceCopy(detail, progress))}</p><div class="progress-form-footer"><label class="progress-sharing"><input name="shared_with_club" type="checkbox"${progress.shared_with_club ? " checked" : ""} /><span><strong>Share with the club</strong><small>Members see your status and page—not your private notes.</small></span></label><button class="primary-button" type="submit">Save progress</button></div></form><aside class="shared-progress-list shared-progress-panel"><div class="shared-progress-heading"><div><p class="eyebrow">Reading together</p><h4>Club progress</h4></div><span>${detail.shared_progress.length} sharing</span></div><div class="shared-reader-list">${sharedMarkup}</div></aside></div>`;
};

const updateReadingProgressPreview = (form, value) => {
  const pace = readingPaceData(participantState.activeBookDetail, { current_page: value });
  const number = form.elements.current_page;
  const range = form.querySelector("[data-page-range]");
  number.value = pace.current;
  range.value = pace.current;
  range.style.setProperty("--range-progress", `${pace.percent}%`);
  form.querySelector("[data-current-page]").textContent = pace.current;
  form.querySelector("[data-progress-percent]").textContent = `${pace.percent}%`;
  const ring = form.querySelector("[data-progress-ring]");
  ring.style.setProperty("--progress", `${pace.percent * 3.6}deg`);
  ring.setAttribute("aria-label", `${pace.percent}% complete`);
  form.querySelector("[data-pages-remaining]").textContent = pace.total ? pace.remaining : "—";
  form.querySelector("[data-days-remaining]").textContent = pace.days ?? "—";
  form.querySelector("[data-pages-daily]").textContent = pace.perDay ?? "—";
  form.querySelector("[data-pages-weekly]").textContent = pace.perWeek ?? "—";
  form.querySelector("#pace-result").textContent = readingPaceCopy(participantState.activeBookDetail, { current_page: pace.current });
};

const bookJourneyNeighbors = (bookId) => {
  const books = participantState.library.previously_read;
  const ids = [...new Set(books.map((book) => book.id))];
  const index = ids.indexOf(Number(bookId));
  return { previous: index > 0 ? ids[index - 1] : null, next: index >= 0 && index < ids.length - 1 ? ids[index + 1] : null };
};

const sessionAttendanceMarkup = (session) => {
  if (session.my_attendance_source === "facilitator") {
    const differs = session.my_participant_report !== null && session.my_participant_report !== session.my_attended;
    return `<div class="session-attendance is-confirmed"><div class="session-attendance-copy"><span class="session-attendance-icon"><svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5" /></svg></span><div><strong>Attendance confirmed</strong><small>The facilitator recorded you as ${session.my_attended ? "attending" : "not attending"}.${differs ? ` Your earlier report was ${session.my_participant_report ? "attended" : "did not attend"}.` : ""}</small></div></div><span class="session-attendance-state">${session.my_attended ? "Attended" : "Did not attend"}</span></div>`;
  }
  const hasReport = session.my_attendance_source === "participant";
  return `<div class="session-attendance ${hasReport ? "has-report" : ""}"><div class="session-attendance-copy"><span class="session-attendance-icon">${hasReport ? '<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5" /></svg>' : "?"}</span><div><strong>${hasReport ? "Your attendance" : "Were you there?"}</strong><small>${hasReport ? "Self-reported and already included in My stats." : "Add this past discussion to your personal reading stats."}</small></div></div><div class="session-attendance-actions" role="group" aria-label="Attendance for ${escapeHtml(formatDate(session.meeting_date))}"><button type="button" data-report-attendance="${session.id}" data-attended="true" class="${session.my_attended === true ? "active" : ""}">I attended</button><button type="button" data-report-attendance="${session.id}" data-attended="false" class="${session.my_attended === false ? "active" : ""}">I didn’t attend</button></div></div>`;
};

const sessionArchiveMarkup = (detail) => {
  const sessions = detail.sessions.filter((session) => session.status === "completed");
  if (!sessions.length) return "";
  return `<section class="book-hub-panel book-session-panel" data-book-hub-panel="session"><div class="book-panel-heading"><div><p class="eyebrow">Previous session</p><h3>${sessions.length === 1 ? "The club’s conversation" : `${sessions.length} club sessions`}</h3></div><p>A participant-safe recap with shared totals and facilitator discussion notes.</p></div><div class="session-archive-stats"><article class="portal-stat-card"><strong>${sessions.length}</strong><span>Session${sessions.length === 1 ? "" : "s"}</span></article><article class="portal-stat-card"><strong>${detail.total_attendance}</strong><span>Total attendance</span></article><article class="portal-stat-card"><strong>${detail.reading_impact_pages.toLocaleString()}</strong><span>Pages read together</span></article><article class="portal-stat-card"><strong>${detail.shared_progress.length}</strong><span>Shared progress updates</span></article></div><div class="session-list">${sessions.map((session) => `<article class="session-summary-card"><header><div><h4>${escapeHtml(formatDate(session.meeting_date))}</h4><small>${escapeHtml([session.meeting_time, session.location].filter(Boolean).join(" · ") || "Meeting details not recorded")}</small></div><strong>${session.attendance_count} of ${session.roster_count} attended</strong></header>${session.discussion_notes ? `<p>${escapeHtml(session.discussion_notes)}</p>` : '<p class="muted">No discussion recap was added.</p>'}${sessionAttendanceMarkup(session)}</article>`).join("")}</div></section>`;
};

const ratingStarsMarkup = (rating, { id, label, outputId }) => `<div class="hero-rating-control" id="${id}" data-rating-output="${outputId}" role="slider" tabindex="0" aria-label="${label}" aria-valuemin="1" aria-valuemax="5" aria-valuestep="0.5" aria-valuenow="${rating || 1}" aria-valuetext="${rating ? `${rating} out of 5 stars` : "Not rated"}">${[1, 2, 3, 4, 5].map((star) => {
  const fill = rating >= star ? 100 : rating >= star - 0.5 ? 50 : 0;
  return `<span class="hero-star" data-rating-star="${star}" aria-hidden="true"><span class="hero-star-empty">★</span><span class="hero-star-fill" style="width:${fill}%">★</span></span>`;
}).join("")}</div>`;

const paintRatingControl = (control, value) => {
  if (!control) return;
  control.querySelectorAll("[data-rating-star]").forEach((star) => {
    const index = Number(star.dataset.ratingStar);
    star.querySelector(".hero-star-fill").style.width = `${value >= index ? 100 : value >= index - 0.5 ? 50 : 0}%`;
  });
  control.setAttribute("aria-valuenow", String(value || 1));
  control.setAttribute("aria-valuetext", value ? `${value} out of 5 stars` : "Not rated");
  const label = document.getElementById(control.dataset.ratingOutput);
  if (label) label.textContent = value ? `${value} out of 5` : "Not rated";
};

const paintHeroRating = (value) => paintRatingControl($("#hero-rating-control"), value);

const ratingFromPointer = (star, clientX) => {
  const bounds = star.getBoundingClientRect();
  const whole = Number(star.dataset.ratingStar);
  return Math.max(1, clientX - bounds.left < bounds.width / 2 ? whole - 0.5 : whole);
};

const saveHeroRating = async (rating) => {
  if (participantState.heroRatingSaving) return;
  participantState.heroRatingSaving = true;
  $("#hero-rating-control")?.setAttribute("aria-busy", "true");
  try {
    await request(`/participant/books/${participantState.activeBookId}/rating`, {
      method: "PUT",
      body: JSON.stringify({ rating, review_text: participantState.activeRating?.review_text || null }),
    });
    delete ratingsState.dataByBook[participantState.activeBookId];
    await Promise.all([loadRatings(), loadActivity(), loadClubActivity()]);
    await openBookPage(participantState.activeBookId);
    toast(`Your ${rating}-star rating was saved.`);
  } catch (error) {
    paintHeroRating(participantState.activeRating?.rating || 0);
    toast(error.message);
  } finally {
    participantState.heroRatingSaving = false;
    $("#hero-rating-control")?.removeAttribute("aria-busy");
  }
};

const openRatingReviewDialog = () => {
  const book = participantState.activeBookDetail?.book;
  if (!book) return;
  const rating = participantState.activeRating?.rating || 3;
  participantState.pendingReviewRating = rating;
  $("#rating-review-heading").textContent = participantState.activeRating ? "Update your review" : "Rate this book";
  $("#rating-review-book").textContent = `${book.title} by ${book.author}`;
  $("#rating-review-cover").src = book.cover_image_url || "/static/assets/library-tools-logo-classic.svg?v=1";
  $("#rating-review-cover").alt = `Cover of ${book.title}`;
  $("#rating-review-stars").innerHTML = `${ratingStarsMarkup(rating, { id: "review-dialog-rating-control", label: "Your rating and review", outputId: "review-dialog-rating-value" })}<output class="rating-value" id="review-dialog-rating-value">${rating} out of 5</output>`;
  $("#rating-review-text").value = participantState.activeRating?.review_text || "";
  $("#rating-review-error").textContent = "";
  $("#rating-review-dialog").showModal();
};

document.addEventListener("click", (event) => {
  if (event.target.closest("[data-open-rating-review]")) openRatingReviewDialog();
  if (event.target.closest("[data-close-rating-review]")) $("#rating-review-dialog").close();
});

$("#rating-review-dialog").addEventListener("pointermove", (event) => {
  const star = event.target.closest("[data-rating-star]");
  if (star) paintRatingControl(star.closest(".hero-rating-control"), ratingFromPointer(star, event.clientX));
});

$("#rating-review-dialog").addEventListener("pointerout", (event) => {
  const control = event.target.closest("#review-dialog-rating-control");
  if (control && !control.contains(event.relatedTarget)) paintRatingControl(control, participantState.pendingReviewRating);
});

$("#rating-review-dialog").addEventListener("click", (event) => {
  const star = event.target.closest("[data-rating-star]");
  if (!star) return;
  participantState.pendingReviewRating = ratingFromPointer(star, event.clientX);
  paintRatingControl(star.closest(".hero-rating-control"), participantState.pendingReviewRating);
});

$("#rating-review-dialog").addEventListener("keydown", (event) => {
  const control = event.target.closest("#review-dialog-rating-control");
  if (!control || !["ArrowLeft", "ArrowDown", "ArrowRight", "ArrowUp", "Home", "End"].includes(event.key)) return;
  event.preventDefault();
  const current = Number(control.getAttribute("aria-valuenow")) || participantState.pendingReviewRating;
  participantState.pendingReviewRating = event.key === "Home" ? 1 : event.key === "End" ? 5 : Math.min(5, Math.max(1, current + (["ArrowRight", "ArrowUp"].includes(event.key) ? 0.5 : -0.5)));
  paintRatingControl(control, participantState.pendingReviewRating);
});

$("#rating-review-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const submit = event.currentTarget.querySelector('[type="submit"]');
  submit.disabled = true;
  try {
    await request(`/participant/books/${participantState.activeBookId}/rating`, {
      method: "PUT",
      body: JSON.stringify({ rating: participantState.pendingReviewRating, review_text: $("#rating-review-text").value.trim() || null }),
    });
    $("#rating-review-dialog").close();
    delete ratingsState.dataByBook[participantState.activeBookId];
    await Promise.all([loadRatings(), loadActivity(), loadClubActivity()]);
    await openBookPage(participantState.activeBookId);
    toast("Your rating and review were saved.");
  } catch (error) {
    $("#rating-review-error").textContent = error.message;
  } finally {
    submit.disabled = false;
  }
});

const discussionMarkup = (posts) => {
  const roots = posts.filter((post) => post.parent_id == null);
  const replies = posts.filter((post) => post.parent_id != null);
  const postMarkup = (post, reply = false) => {
    const childReplies = reply ? [] : replies.filter((item) => item.parent_id === post.id);
    return `<article class="${reply ? "discussion-reply" : "discussion-thread"}"><header class="discussion-author">${avatarMarkup(post.author)}<div><strong>${escapeHtml(post.author.name)}</strong><small class="user-meta">${escapeHtml(formatTimestamp(post.created_at))}</small></div>${post.spoiler ? '<span class="spoiler-badge">Spoiler</span>' : ""}</header><p class="discussion-body${post.spoiler ? " spoiler-text" : ""}"${post.spoiler ? ` data-reveal-spoiler="true" data-body="${escapeHtml(post.body)}"` : ""}>${post.spoiler ? "Tap to reveal this comment" : escapeHtml(post.body)}</p><div class="post-meeting-actions discussion-actions"><button class="quiet-button reaction-button${post.reacted_by_me ? " is-active" : ""}" type="button" data-react-post="${post.id}" aria-label="${post.reacted_by_me ? "Remove reaction" : "React to this post"}"><svg class="icon" viewBox="0 0 24 24" fill="${post.reacted_by_me ? "currentColor" : "none"}" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M2 9.5a5.5 5.5 0 0 1 9.591-3.676.56.56 0 0 0 .818 0A5.49 5.49 0 0 1 22 9.5c0 2.29-1.5 4-3 5.5l-5.492 5.313a2 2 0 0 1-3 .019L5 15c-1.5-1.5-3-3.2-3-5.5" /></svg> <span>${post.reaction_count}</span></button>${reply ? "" : `<button class="quiet-button" type="button" data-detail-reply="${post.id}">Reply</button>`}${post.author.is_self ? `<button class="quiet-button" type="button" data-detail-delete-post="${post.id}">Delete</button>` : ""}</div>${reply ? "" : `<form class="reply-form thread-reply-form" data-detail-reply-form="${post.id}" hidden><textarea rows="2" maxlength="4000" placeholder="Add to this thread…"></textarea><div><label><input type="checkbox" name="spoiler" /> Contains spoilers</label><button class="secondary-button" type="submit">Post reply</button></div></form>${childReplies.length ? `<div class="discussion-replies"><p class="reply-count">${childReplies.length} ${childReplies.length === 1 ? "reply" : "replies"}</p>${childReplies.map((item) => postMarkup(item, true)).join("")}</div>` : ""}`}</article>`;
  };
  return roots.length ? roots.map((post) => postMarkup(post)).join("") : '<p class="muted">No posts yet. Start the conversation.</p>';
};

const staticRatingMarkup = (rating) => `<span class="static-rating-stars" style="--rating-width:${Math.max(0, Math.min(100, (Number(rating) / 5) * 100))}%" role="img" aria-label="${rating} out of 5 stars"><span aria-hidden="true">★★★★★</span><span aria-hidden="true">★★★★★</span></span>`;

const ratingsAndReviewsMarkup = (ratings, mine) => {
  const scores = [5, 4.5, 4, 3.5, 3, 2.5, 2, 1.5, 1];
  const buckets = scores.map((score) => ({
    score,
    count: ratings.ratings.filter((item) => item.rating === score).length,
  })).filter((item) => item.count > 0);
  const maxCount = Math.max(1, ...buckets.map((item) => item.count));
  const writtenCount = ratings.ratings.filter((item) => item.review_text).length;
  const reviews = ratings.ratings.length
    ? ratings.ratings.map((item) => {
      const initial = Array.from(item.participant_name || "?")[0]?.toLocaleUpperCase() || "?";
      const isMine = item.participant_id === ratingsState.participantId;
      return `<article class="reader-review${isMine ? " is-mine" : ""}"><div class="review-reader"><span class="review-avatar">${escapeHtml(initial)}</span><div><strong>${escapeHtml(item.participant_name)}${isMine ? " (you)" : ""}</strong>${staticRatingMarkup(item.rating)}</div></div><blockquote class="review-copy${item.review_text ? "" : " is-empty"}">${item.review_text ? `“${escapeHtml(item.review_text)}”` : "Rated without a written review."}</blockquote><strong class="review-number">${item.rating}</strong></article>`;
    }).join("")
    : '<div class="ratings-empty"><span aria-hidden="true"><svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11.525 2.295a.53.53 0 0 1 .95 0l2.31 4.679a2.123 2.123 0 0 0 1.595 1.16l5.166.756a.53.53 0 0 1 .294.904l-3.736 3.638a2.123 2.123 0 0 0-.611 1.878l.882 5.14a.53.53 0 0 1-.771.56l-4.618-2.428a2.122 2.122 0 0 0-1.973 0L6.396 21.01a.53.53 0 0 1-.77-.56l.881-5.139a2.122 2.122 0 0 0-.611-1.879L2.16 9.795a.53.53 0 0 1 .294-.906l5.165-.755a2.122 2.122 0 0 0 1.597-1.16z" /></svg></span><p><strong>No ratings yet.</strong><br />Be the first reader to share a reaction.</p></div>';
  return `<div class="ratings-overview"><section class="ratings-score-card"><p class="eyebrow">Club average</p><strong class="ratings-score">${ratings.average ?? "—"}</strong>${ratings.average != null ? staticRatingMarkup(ratings.average) : ""}<p>${ratings.count} reader${ratings.count === 1 ? "" : "s"} rated this book</p><button class="ratings-review-button" type="button" data-open-rating-review>${mine?.review_text ? "Edit your review" : "Write a review"}</button></section><section class="ratings-breakdown"><div><p class="eyebrow">Rating spread</p><h4>How the club rated it</h4></div><div class="rating-distribution">${buckets.length ? buckets.map((item) => `<div class="rating-distribution-row"><span>${item.score}★</span><div><span style="width:${(item.count / maxCount) * 100}%"></span></div><strong>${item.count}</strong></div>`).join("") : '<p class="muted">The distribution will appear when readers rate the book.</p>'}</div></section></div><div class="reviews-heading"><div><p class="eyebrow">Reader reviews</p><h4>What the club thought</h4></div><span>${writtenCount} written · ${ratings.count} rated</span></div><div class="reader-review-list">${reviews}</div>`;
};

const renderBookPage = ({ detail, ratings, progress, posts }) => {
  const book = detail.book;
  const mine = ratings.ratings.find((item) => item.participant_id === ratingsState.participantId);
  participantState.activeRating = mine || null;
  const tab = participantState.bookHubTab;
  const hasSession = detail.sessions.some((session) => session.status === "completed");
  const isCurrentBook = participantState.upcomingMeeting?.meeting?.book?.id === book.id;
  const neighbors = bookJourneyNeighbors(book.id);
  $("#book-detail-journey-nav").innerHTML = hasSession ? `${neighbors.previous ? `<button class="quiet-button" type="button" data-open-book="${neighbors.previous}"><svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m15 18-6-6 6-6" /></svg> Previous book</button>` : ""}${neighbors.next ? `<button class="quiet-button" type="button" data-open-book="${neighbors.next}">Next book <svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m9 18 6-6-6-6" /></svg></button>` : ""}` : "";
  const bookActivity = participantState.clubActivity.filter((item) => item.book.id === book.id && item.kind !== "discussion");
  const activityMarkup = bookActivity.length
    ? `<aside class="conversation-activity" aria-label="Recent club activity"><span class="conversation-activity-label">Latest</span><div class="conversation-updates">${bookActivity.slice(0, 4).map((item) => `<article class="conversation-update">${avatarMarkup(item.actor)}<div><strong>${escapeHtml(item.actor.name)}</strong><span>${item.kind === "rating" ? escapeHtml((item.detail || "rated").replace(" stars", "★")) : escapeHtml((item.detail || "updated progress").replace("reading · ", ""))}</span></div></article>`).join("")}</div></aside>`
    : "";
  const tabs = [...(hasSession ? [["session", "Session recap"]] : []), ["conversation","Conversation"],["ratings","Ratings and Reviews"],["progress","Reading progress"]];
  $("#book-page-content").innerHTML = `<div class="book-page-hero"><div class="book-page-visual"><img class="book-page-cover" src="${escapeHtml(book.cover_image_url || "/static/assets/library-tools-logo-classic.svg?v=1")}" alt="" /><div class="hero-rating-row"><span class="hero-rating-label">${isCurrentBook ? "Your rating so far" : "Your rating"}</span><div class="hero-rating-picker">${ratingStarsMarkup(mine?.rating || 0, { id: "hero-rating-control", label: "Your rating", outputId: "hero-rating-value" })}<output id="hero-rating-value">${mine ? `${mine.rating} out of 5` : "Not rated"}</output></div><button class="hero-review-link" type="button" data-open-rating-review>${mine?.review_text ? "Edit your review" : "Write a review"}</button></div></div><div class="book-page-intro"><p class="eyebrow">${escapeHtml(book.author)}</p><h2>${escapeHtml(book.title)}</h2><div class="book-quick-meta"><span>${book.page_count ? `${book.page_count} pages` : "Page count unavailable"}</span><span>${ratings.average != null ? `${ratings.average}★ from ${ratings.count}` : "No ratings yet"}</span>${hasSession ? "<span>Previously read</span>" : ""}</div><section class="book-blurb" aria-label="About this book"><strong>About this book</strong><p>${escapeHtml(book.description || "No description has been added yet.")}</p>${book.genres ? `<small>${escapeHtml(book.genres)}</small>` : ""}</section>${isCurrentBook ? meetingHeroMarkup(participantState.upcomingMeeting) : ""}</div></div>
    <div class="book-hub-tabs" role="tablist" aria-label="Book sections">${tabs.map(([value,label]) => `<button type="button" role="tab" data-book-hub-tab="${value}" aria-selected="${tab === value}" class="${tab === value ? "active" : ""}">${label}${value === "conversation" && posts.length ? ` <span>${posts.length}</span>` : ""}</button>`).join("")}</div>
    ${sessionArchiveMarkup(detail)}
    <section class="book-hub-panel conversation-panel" data-book-hub-panel="conversation"${tab === "conversation" ? "" : " hidden"}><div class="book-panel-heading conversation-heading"><div><p class="eyebrow">Club conversation</p><h3>What readers are noticing</h3></div><p>${posts.length} contribution${posts.length === 1 ? "" : "s"} across ${posts.filter((post) => post.parent_id == null).length} thread${posts.filter((post) => post.parent_id == null).length === 1 ? "" : "s"}.</p></div>${activityMarkup}<form class="discussion-compose conversation-composer" id="detail-discussion-form"><div class="composer-intro"><span aria-hidden="true"><svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11.017 2.814a1 1 0 0 1 1.966 0l1.051 5.558a2 2 0 0 0 1.594 1.594l5.558 1.051a1 1 0 0 1 0 1.966l-5.558 1.051a2 2 0 0 0-1.594 1.594l-1.051 5.558a1 1 0 0 1-1.966 0l-1.051-5.558a2 2 0 0 0-1.594-1.594l-5.558-1.051a1 1 0 0 1 0-1.966l5.558-1.051a2 2 0 0 0 1.594-1.594z" /></svg></span><div><strong>Start a new thread</strong><small>Share a question, passage, or thought with the club.</small></div></div><textarea rows="2" maxlength="4000" placeholder="What’s on your mind about this book?"></textarea><div class="composer-actions"><label><input type="checkbox" name="spoiler" /> Contains spoilers</label><button class="primary-button" type="submit">Post to club</button></div></form><div class="conversation-thread-grid" id="detail-discussion-list">${discussionMarkup(posts)}</div></section>
    <section class="book-hub-panel ratings-panel" data-book-hub-panel="ratings"${tab === "ratings" ? "" : " hidden"}>${ratingsAndReviewsMarkup(ratings, mine)}</section>
    <section class="book-hub-panel" data-book-hub-panel="progress"${tab === "progress" ? "" : " hidden"}><div class="book-panel-heading progress-panel-heading"><div><p class="eyebrow">Reading progress</p><h3>Stay on pace</h3></div><p>Move the page marker to see the pace you need before book club day${detail.meeting_date ? ` on ${escapeHtml(formatDate(detail.meeting_date))}` : ""}.</p></div>${readingProgressMarkup(detail, progress)}</section>`;
  document.querySelectorAll("[data-book-hub-panel]").forEach((panel) => { panel.hidden = panel.dataset.bookHubPanel !== tab; });
};

const openBookPage = async (bookId, { scroll = false, portalView = participantState.portalView === "book" ? "book" : "home", updateHistory = false } = {}) => {
  const changedBook = participantState.activeBookId !== Number(bookId);
  participantState.activeBookId = Number(bookId);
  const id = participantState.activeBookId;
  const [detail, ratings, progress, posts] = await Promise.all([
    request(`/participant/books/${id}/detail`), request(`/participant/books/${id}/ratings`),
    request(`/participant/books/${id}/reading-progress`), request(`/participant/books/${id}/discussion`),
  ]);
  if (changedBook) participantState.bookHubTab = portalView === "book" && detail.sessions.some((session) => session.status === "completed") ? "session" : "conversation";
  participantState.activeBookDetail = detail;
  const workspace = $("#book-page-section");
  $(portalView === "book" ? "#book-detail-slot" : "#home-book-slot").append(workspace);
  workspace.querySelector(".book-stage-kicker").innerHTML = portalView === "book" ? "<span></span>Club book" : "<span></span>Current club read";
  renderBookPage({ detail, ratings, progress, posts });
  setPortalView(portalView, { updateHistory: false });
  if (updateHistory) history.pushState({ view: portalView, bookId: id }, "", portalView === "book" ? `${location.pathname}?view=book&book=${id}` : location.pathname);
  if (scroll) $("#book-page-section").scrollIntoView({ behavior: "smooth", block: "start" });
};

document.addEventListener("click", (event) => { const button = event.target.closest("[data-open-book]"); if (button) openBookPage(button.dataset.openBook, { scroll: true, portalView: "book", updateHistory: true }).catch((error) => toast(error.message)); });
document.addEventListener("keydown", (event) => { const card = event.target.closest('[data-open-book][role="button"]'); if (card && (event.key === "Enter" || event.key === " ")) { event.preventDefault(); card.click(); } });
$("#book-page-content").addEventListener("input", (event) => {
  if ((event.target.name === "current_page" || event.target.matches("[data-page-range]")) && event.target.closest("#detail-progress-form")) {
    updateReadingProgressPreview(event.target.closest("#detail-progress-form"), Number(event.target.value || 0));
  }
});
$("#book-page-content").addEventListener("pointermove", (event) => {
  const star = event.target.closest("[data-rating-star]");
  if (star) paintRatingControl(star.closest(".hero-rating-control"), ratingFromPointer(star, event.clientX));
});
$("#book-page-content").addEventListener("pointerout", (event) => {
  const control = event.target.closest(".hero-rating-control");
  if (control && !control.contains(event.relatedTarget)) paintRatingControl(control, participantState.activeRating?.rating || 0);
});
$("#book-page-content").addEventListener("keydown", (event) => {
  const control = event.target.closest(".hero-rating-control");
  if (!control || !["ArrowLeft", "ArrowDown", "ArrowRight", "ArrowUp", "Home", "End"].includes(event.key)) return;
  event.preventDefault();
  const current = Number(control.getAttribute("aria-valuenow")) || participantState.activeRating?.rating || 1;
  const rating = event.key === "Home" ? 1 : event.key === "End" ? 5 : Math.min(5, Math.max(1, current + (["ArrowRight", "ArrowUp"].includes(event.key) ? 0.5 : -0.5)));
  paintRatingControl(control, rating);
  clearTimeout(saveHeroRating.keyboardTimer);
  saveHeroRating.keyboardTimer = setTimeout(() => saveHeroRating(rating), 350);
});
$("#book-page-content").addEventListener("click", async (event) => {
  const attendanceButton = event.target.closest("[data-report-attendance]");
  if (attendanceButton) {
    const meetingId = Number(attendanceButton.dataset.reportAttendance);
    const attended = attendanceButton.dataset.attended === "true";
    const group = attendanceButton.closest(".session-attendance-actions");
    group?.querySelectorAll("button").forEach((button) => { button.disabled = true; });
    try {
      await request(`/participant/meetings/${meetingId}/attendance`, {
        method: "PUT",
        body: JSON.stringify({ attended }),
      });
      await Promise.all([loadStats(), loadActivity()]);
      await openBookPage(participantState.activeBookId);
      toast(attended ? "Attendance added to My stats." : "Attendance updated.");
    } catch (error) {
      group?.querySelectorAll("button").forEach((button) => { button.disabled = false; });
      toast(error.message);
    }
    return;
  }
  const ratingStar = event.target.closest("[data-rating-star]");
  if (ratingStar) {
    const control = ratingStar.closest(".hero-rating-control");
    const rating = ratingFromPointer(ratingStar, event.clientX);
    paintRatingControl(control, rating);
    await saveHeroRating(rating);
    return;
  }
  const tabButton = event.target.closest("[data-book-hub-tab], [data-book-hub-tab-target]");
  if (tabButton) {
    const selected = tabButton.dataset.bookHubTab || tabButton.dataset.bookHubTabTarget;
    participantState.bookHubTab = selected;
    document.querySelectorAll("[data-book-hub-tab]").forEach((button) => {
      const active = button.dataset.bookHubTab === selected;
      button.classList.toggle("active", active);
      button.setAttribute("aria-selected", String(active));
    });
    document.querySelectorAll("[data-book-hub-panel]").forEach((panel) => { panel.hidden = panel.dataset.bookHubPanel !== selected; });
    document.querySelector(`[data-book-hub-panel="${selected}"]`)?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    return;
  }
  const spoiler = event.target.closest("[data-reveal-spoiler]");
  if (spoiler) { spoiler.classList.add("revealed"); spoiler.textContent = spoiler.dataset.body || ""; return; }
  const reply = event.target.closest("[data-detail-reply]");
  if (reply) { $(`[data-detail-reply-form='${reply.dataset.detailReply}']`).hidden = false; return; }
  const react = event.target.closest("[data-react-post]");
  const remove = event.target.closest("[data-detail-delete-post]");
  try {
    if (react) await request(`/participant/discussion/${react.dataset.reactPost}/reaction`, { method: "PUT" });
    else if (remove) await request(`/participant/discussion/${remove.dataset.detailDeletePost}`, { method: "DELETE" });
    else return;
    delete ratingsState.dataByBook[participantState.activeBookId];
    await Promise.all([loadRatings(), loadActivity(), loadClubActivity()]);
    await openBookPage(participantState.activeBookId);
    toast("Saved.");
  } catch (error) { toast(error.message); }
});
$("#book-page-content").addEventListener("submit", async (event) => {
  event.preventDefault();
  const id = participantState.activeBookId;
  try {
    if (event.target.id === "detail-progress-form") {
      const form = event.target;
      await request(`/participant/books/${id}/reading-progress`, { method: "PUT", body: JSON.stringify({ status: form.elements.status.value, current_page: Number(form.elements.current_page.value), shared_with_club: form.elements.shared_with_club.checked }) });
    } else {
      const form = event.target;
      const parentId = form.dataset.detailReplyForm ? Number(form.dataset.detailReplyForm) : null;
      const textarea = form.querySelector("textarea");
      if (!textarea.value.trim()) return;
      await request(`/participant/books/${id}/discussion`, { method: "POST", body: JSON.stringify({ body: textarea.value.trim(), parent_id: parentId, spoiler: form.elements.spoiler.checked }) });
    }
    await Promise.all([loadCurrentReading(), loadActivity(), loadClubActivity()]);
    await openBookPage(id);
    toast("Saved.");
  } catch (error) { toast(error.message); }
});

const profileInitials = (name = "Reader") => name.trim().split(/\s+/).slice(0, 2).map((part) => part[0] || "").join("").toUpperCase() || "R";
const refreshProfilePreview = () => {
  const form = $("#profile-form");
  const preview = $("#profile-avatar-preview");
  const avatarUrl = form.elements.avatar_url.value.trim();
  preview.textContent = profileInitials(form.elements.name.value);
  preview.style.backgroundImage = avatarUrl ? `url("${avatarUrl.replace(/["\\]/g, "")}")` : "";
  preview.classList.toggle("has-image", Boolean(avatarUrl));
  $("#profile-bio-count").textContent = form.elements.bio.value.length.toLocaleString();
};

const openProfileDialog = async () => {
  try {
    participantState.profile = participantState.profile || await request("/participant/profile");
    const form = $("#profile-form");
    form.elements.name.value = participantState.profile.name;
    form.elements.avatar_url.value = participantState.profile.avatar_url || "";
    form.elements.bio.value = participantState.profile.bio || "";
    form.elements.directory_visible.checked = participantState.profile.directory_visible;
    refreshProfilePreview();
    $("#profile-error").textContent = "";
    $("#profile-dialog").showModal();
  } catch (error) { toast(error.message); }
};

$("#profile-settings").addEventListener("click", openProfileDialog);
$("#edit-directory-profile").addEventListener("click", openProfileDialog);
$("#close-profile-dialog").addEventListener("click", () => $("#profile-dialog").close());
$("#profile-form").addEventListener("input", (event) => {
  if (["name", "avatar_url", "bio"].includes(event.target.name)) refreshProfilePreview();
});
$("#profile-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const button = form.querySelector("button[type=submit]");
  button.disabled = true;
  button.textContent = "Saving…";
  try {
    participantState.profile = await request("/participant/profile", {
      method: "PUT",
      body: JSON.stringify({
        name: form.elements.name.value,
        avatar_url: form.elements.avatar_url.value || null,
        bio: form.elements.bio.value || null,
        directory_visible: form.elements.directory_visible.checked,
      }),
    });
    $("#profile-dialog").close();
    $("#welcome-heading").textContent = timeBasedGreeting(participantState.profile.name);
    await loadDirectory();
    toast("Profile saved.");
  } catch (error) { $("#profile-error").textContent = error.message; }
  finally { button.disabled = false; button.textContent = "Save profile"; }
});

const renderDiscussion = (book, posts) => {
  const section = $("#discussion-section");
  section.hidden = false;
  section.dataset.bookId = book.id;
  $("#discussion-heading").textContent = `Discuss ${book.title}`;
  const roots = posts.filter((post) => post.parent_id == null);
  const replies = posts.filter((post) => post.parent_id != null);
  $("#discussion-list").innerHTML = roots.length ? roots.map((post) => {
    const postReplies = replies.filter((reply) => reply.parent_id === post.id);
    return `<article class="discussion-thread"><div class="discussion-author">${avatarMarkup(post.author)}<div><strong>${escapeHtml(post.author.name)}</strong><small class="user-meta">${escapeHtml(formatTimestamp(post.created_at))}</small></div></div><p class="discussion-body">${escapeHtml(post.body)}</p><div class="post-meeting-actions"><button class="quiet-button" type="button" data-reply-to="${post.id}">Reply</button>${post.author.is_self ? `<button class="quiet-button" type="button" data-delete-post="${post.id}">Delete</button>` : ""}</div><form class="reply-form" data-reply-form="${post.id}" hidden><textarea rows="2" maxlength="4000" placeholder="Write a reply"></textarea><button class="secondary-button" type="submit">Post reply</button></form><div class="discussion-replies">${postReplies.map((reply) => `<div class="discussion-reply"><div class="discussion-author">${avatarMarkup(reply.author)}<div><strong>${escapeHtml(reply.author.name)}</strong><small class="user-meta">${escapeHtml(formatTimestamp(reply.created_at))}</small></div></div><p class="discussion-body">${escapeHtml(reply.body)}</p>${reply.author.is_self ? `<button class="quiet-button" type="button" data-delete-post="${reply.id}">Delete</button>` : ""}</div>`).join("")}</div></article>`;
  }).join("") : '<p class="muted">No posts yet. Start the conversation.</p>';
};

const loadDiscussion = async (bookId) => {
  const book = participantState.books.find((item) => item.id === Number(bookId));
  if (!book) return;
  renderDiscussion(book, await request(`/participant/books/${book.id}/discussion`));
};

$("#discussion-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const bookId = Number($("#discussion-section").dataset.bookId);
  const body = $("#discussion-body").value.trim();
  if (!body) { toast("Write something before posting."); return; }
  try {
    await request(`/participant/books/${bookId}/discussion`, { method: "POST", body: JSON.stringify({ body }) });
    $("#discussion-body").value = "";
    await loadDiscussion(bookId);
    toast("Posted to the discussion.");
  } catch (error) { toast(error.message); }
});

$("#discussion-list").addEventListener("click", async (event) => {
  const reply = event.target.closest("[data-reply-to]");
  if (reply) { $("[data-reply-form='" + reply.dataset.replyTo + "']").hidden = false; return; }
  const remove = event.target.closest("[data-delete-post]");
  if (!remove) return;
  try {
    await request(`/participant/discussion/${remove.dataset.deletePost}`, { method: "DELETE" });
    await loadDiscussion(Number($("#discussion-section").dataset.bookId));
    toast("Post deleted.");
  } catch (error) { toast(error.message); }
});

$("#discussion-list").addEventListener("submit", async (event) => {
  const form = event.target.closest("[data-reply-form]");
  if (!form) return;
  event.preventDefault();
  const body = form.querySelector("textarea").value.trim();
  if (!body) return;
  const bookId = Number($("#discussion-section").dataset.bookId);
  try {
    await request(`/participant/books/${bookId}/discussion`, { method: "POST", body: JSON.stringify({ body, parent_id: Number(form.dataset.replyForm) }) });
    await loadDiscussion(bookId);
    toast("Reply posted.");
  } catch (error) { toast(error.message); }
});

document.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-open-discussion-book]");
  if (!button) return;
  try {
    await loadDiscussion(Number(button.dataset.openDiscussionBook));
    $("#discussion-section").scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (error) { toast(error.message); }
});

const loadClubSwitcher = async (activeSlug) => {
  const clubs = await request("/participant/auth/clubs");
  $("#club-switcher").innerHTML = clubs.map((club) => `<option value="${escapeHtml(club.slug)}"${club.slug === activeSlug ? " selected" : ""}>${escapeHtml(club.name)}</option>`).join("");
  $("#club-switcher").hidden = clubs.length < 2;
};

$("#club-switcher").addEventListener("change", async (event) => {
  try {
    await request(`/participant/auth/clubs/${encodeURIComponent(event.target.value)}/select`, { method: "POST" });
    location.reload();
  } catch (error) { toast(error.message); }
});

let notificationPreferences = null;
const loadNotificationPreferences = async () => {
  notificationPreferences = await request("/participant/notification-preferences");
  return notificationPreferences;
};

$("#notification-settings").addEventListener("click", async () => {
  try {
    const preferences = notificationPreferences || await loadNotificationPreferences();
    const form = $("#notification-form");
    ["announcements", "polls", "meeting_reminders", "discussion_replies"].forEach((name) => { form.elements[name].checked = preferences[name]; });
    form.elements.delivery_frequency.value = preferences.delivery_frequency;
    $("#notification-error").textContent = "";
    $("#notification-dialog").showModal();
  } catch (error) { toast(error.message); }
});
$("#close-notification-dialog").addEventListener("click", () => $("#notification-dialog").close());
$("#notification-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const button = form.querySelector("button[type=submit]");
  button.disabled = true;
  button.textContent = "Saving…";
  const data = Object.fromEntries(["announcements", "polls", "meeting_reminders", "discussion_replies"].map((name) => [name, form.elements[name].checked]));
  data.delivery_frequency = form.elements.delivery_frequency.value;
  try {
    notificationPreferences = await request("/participant/notification-preferences", { method: "PUT", body: JSON.stringify(data) });
    $("#notification-dialog").close();
    toast("Notification preferences saved.");
  } catch (error) { $("#notification-error").textContent = error.message; }
  finally { button.disabled = false; button.textContent = "Save preferences"; }
});

(async () => {
  try {
    const participant = await request("/participant/auth/me");
    participantState.participant = participant;
    render(participant);
    ratingsState.participantId = participant.id;
    participantState.participantId = participant.id;
    [participantState.books, participantState.library, participantState.latestCompletedMeeting, participantState.profile] = await Promise.all([
      request("/participant/books"),
      request("/participant/books/library"),
      request("/participant/meetings/latest-completed"),
      request("/participant/profile"),
      loadClubSwitcher(participant.club_slug),
    ]);
    await Promise.all([loadAnnouncements(), loadRsvp(), loadVoting(), loadDatePoll(), loadRatings(), loadActivity(), loadClubActivity(), loadNotificationPreferences(), loadDirectory(), loadStats()]);
    const params = new URLSearchParams(location.search);
    const requestedView = params.get("view") || "home";
    const requestedBook = params.get("book");
    const featuredBook = participantState.library.current[0]
        || participantState.library.previously_read[0]
        || participantState.books[0];
    participantState.homeBookId = featuredBook?.id || null;
    const detailBook = requestedBook ? participantState.books.find((book) => book.id === Number(requestedBook)) : null;
    if (requestedView === "book" && detailBook) await openBookPage(detailBook.id, { portalView: "book", updateHistory: false });
    else if (featuredBook) {
      await openBookPage(featuredBook.id, { portalView: "home", updateHistory: false });
      if (requestedView !== "home") setPortalView(requestedView, { updateHistory: false });
    }
    else {
      $("#book-page-content").innerHTML = '<div class="book-page-empty"><h2>Your club’s next read will live here</h2><p>Once a book is scheduled, members can track progress, rate it, and discuss it together.</p></div>';
      setPortalView(requestedView, { updateHistory: false });
    }
    renderPostMeeting();
    renderActionCenter();
    startAnnouncementRefresh();
  } catch {
    location.href = "/";
  }
})();
