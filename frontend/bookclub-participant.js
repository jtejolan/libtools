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

const formatDate = (value) =>
  new Intl.DateTimeFormat(undefined, { weekday: "short", month: "short", day: "numeric", year: "numeric" }).format(
    new Date(`${value}T12:00:00`),
  );

const render = (participant) => {
  document.title = `${participant.club_name} — Book Club`;
  $("#club-eyebrow").textContent = participant.club_name;
  $("#welcome-heading").textContent = `Welcome, ${capitalizeFirst(participant.name)}`;

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
};

const portalViewCopy = {
  books: ["The club shelf", "Books", "Browse current, upcoming, and previously read selections in one cover-forward collection."],
  personal: ["Your reading journey", "My stats", "A private view of the books, meetings, ratings, and choices that make up your club experience."],
  club: ["Reading together", "Club stats", "The collective story of your club—shared as totals and trends, never as a member leaderboard."],
  members: ["Your reading community", "Members", "Meet the readers who have chosen to appear in the club directory."],
};

const portalHeading = (view) => {
  const [eyebrow, title, intro] = portalViewCopy[view];
  return `<header class="portal-page-heading"><div><p class="eyebrow">${eyebrow}</p><h1>${title}</h1><p class="intro">${intro}</p></div></header>`;
};

const initializePortalShell = () => {
  const main = $("main.dashboard");
  const header = $(".site-header");
  header.insertAdjacentHTML("afterend", `<nav class="participant-portal-nav" aria-label="Participant portal">${[
    ["home", "Home"], ["books", "Books"], ["personal", "My stats"], ["club", "Club stats"], ["members", "Members"],
  ].map(([view, label]) => `<button type="button" data-portal-nav="${view}">${label}</button>`).join("")}</nav>`);

  const home = document.createElement("section");
  home.className = "portal-view";
  home.dataset.portalView = "home";
  [".participant-heading", "#email-panel", "#book-page-section", ".support-heading", ".participant-grid", ".decisions-disclosure", ".legacy-participant-sections"].forEach((selector) => home.append($(selector)));
  const homeBookSlot = document.createElement("div");
  homeBookSlot.id = "home-book-slot";
  home.insertBefore(homeBookSlot, home.querySelector(".support-heading"));
  homeBookSlot.append(home.querySelector("#book-page-section"));

  const books = document.createElement("section");
  books.className = "portal-view";
  books.dataset.portalView = "books";
  books.innerHTML = portalHeading("books");
  books.append($("#library-section"));
  const libraryHeading = books.querySelector(".library-heading");
  libraryHeading.querySelector(".eyebrow").textContent = "Find your next book";
  libraryHeading.querySelector("h2").textContent = "The complete shelf";
  libraryHeading.querySelector(".library-note").textContent = "Search the collection or narrow it to what the club is reading now, next, or has already discussed.";
  const search = libraryHeading.querySelector("#library-search");
  const controls = document.createElement("div");
  controls.className = "library-controls";
  controls.innerHTML = '<select id="library-status-filter" aria-label="Filter books"><option value="all">All books</option><option value="current">Current</option><option value="up_next">Coming up</option><option value="previously_read">Previously read</option></select><select id="library-sort" aria-label="Sort books"><option value="journey">Club journey</option><option value="title">Title</option><option value="rating">Highest rated</option></select>';
  controls.prepend(search);
  libraryHeading.append(controls);

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
  members.append($(".members-section"));
  members.querySelector(".members-section .section-toolbar>div").hidden = true;

  const book = document.createElement("section");
  book.className = "portal-view";
  book.dataset.portalView = "book";
  book.innerHTML = '<div class="book-detail-toolbar"><button class="quiet-button" id="book-detail-back" type="button">← Back to books</button><p>Use the previous and next books to move through the club journey.</p></div><div id="book-detail-slot"></div>';
  main.replaceChildren(home, books, personal, club, members, book);
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
  participantState.announcements = announcements;
  const latest = announcements[0];
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
      ${data.video_call_url ? `<a class="calendar-link" href="${escapeHtml(data.video_call_url)}" target="_blank" rel="noopener">Join online ↗</a>` : ""}
    </div>
    <div class="meeting-actions">
      ${options.map(([status, label]) => `<button class="${data.rsvp_status === status ? "primary-button" : "secondary-button"}" data-rsvp="${status}" data-meeting-id="${meeting.id}">${label}</button>`).join("")}
    </div>
    <div class="calendar-actions"><a class="calendar-link" href="${escapeHtml(data.google_calendar_url)}" target="_blank" rel="noopener">Add to Google Calendar ↗</a><a class="calendar-link" href="${escapeHtml(data.ics_calendar_url)}" download>Download calendar invite</a></div>
    <p class="book-meeting-note">${data.rsvp_status ? "Your RSVP is saved. You can change it anytime before the meeting." : "RSVP so your facilitator can plan."}</p>
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
  $("#current-book-detail").innerHTML = `${book.description ? `<p>${escapeHtml(book.description)}</p>` : '<p class="muted">No description has been added yet.</p>'}${book.page_count ? `<p class="user-meta">${book.page_count} pages${book.genres ? ` · ${escapeHtml(book.genres)}` : ""}</p>` : ""}${book.catalogue_url ? `<a class="calendar-link" href="${escapeHtml(book.catalogue_url)}" target="_blank" rel="noopener">Find it in the catalogue ↗</a>` : ""}`;
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
  return `<article class="participant-book-card" data-open-book="${book.id}" data-book-id="${book.id}" tabindex="0" role="button" aria-label="Open ${escapeHtml(book.title)}"><img src="${escapeHtml(book.cover_image_url || "/static/assets/library-tools-logo-classic.svg?v=1")}" alt="" loading="lazy" /><div class="participant-book-card-copy"><span class="book-status ${statusClass}">${statusCopy}</span><h3>${escapeHtml(book.title)}</h3><p>${escapeHtml(book.author)}</p><div class="participant-book-card-meta">${book.page_count ? `<span>${book.page_count} pages</span>` : ""}${ratingsData.count ? `<span>${ratingsData.average}★ club</span>` : "<span>Not rated</span>"}${mine ? `<span>You: ${mine.rating}★</span>` : ""}</div></div><span class="book-open-cue">Open →</span></article>`;
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
  list.innerHTML = visible.length ? `<div class="participant-book-grid">${visible.map(({ book, status }) => renderBookRatingCard(book, ratingsState.dataByBook[book.id], status)).join("")}</div>` : '<p class="muted">No books match your search.</p>';
  renderPostMeeting();
  renderActionCenter();
};

$("#library-search").addEventListener("input", () => loadRatings().catch((error) => toast(error.message)));
$("#library-status-filter").addEventListener("change", () => loadRatings().catch((error) => toast(error.message)));
$("#library-sort").addEventListener("change", () => loadRatings().catch((error) => toast(error.message)));

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

const statCardsMarkup = (items) => `<div class="portal-stat-grid">${items.map(([value, label]) => `<article class="portal-stat-card"><strong>${escapeHtml(String(value))}</strong><span>${escapeHtml(label)}</span></article>`).join("")}</div>`;

const statBarsMarkup = (items, emptyCopy) => {
  if (!items.length) return `<p class="muted">${escapeHtml(emptyCopy)}</p>`;
  const maximum = Math.max(...items.map((item) => item.value), 1);
  return `<div class="stat-bar-list">${items.map((item) => `<div class="stat-bar-row"><strong>${escapeHtml(item.label)}</strong><div class="stat-bar-track"><span style="width:${Math.round((item.value / maximum) * 100)}%"></span></div><b>${item.value}</b></div>`).join("")}</div>`;
};

const renderPersonalStats = (stats) => {
  participantState.personalStats = stats;
  $("#personal-stats-content").innerHTML = `${statCardsMarkup([
    [stats.meetings_attended, "Meetings attended"],
    [stats.books_read, "Books read"],
    [stats.pages_read.toLocaleString(), "Pages read"],
    [stats.books_rated, "Books rated"],
  ])}<div class="stats-layout"><section class="stats-panel"><p class="eyebrow">Your taste</p><h2>Favourite genres</h2>${statBarsMarkup(stats.favourite_genres, "Attend a completed meeting to begin your genre portrait.")}</section><section class="stats-panel"><p class="eyebrow">Your ratings</p><h2>${stats.average_rating == null ? "No ratings yet" : `${stats.average_rating}★ average`}</h2>${statBarsMarkup(stats.rating_distribution, "Your rating pattern will appear after you rate a book.")}</section><section class="stats-panel"><p class="eyebrow">Reading now</p><h2>Your shelf</h2>${statCardsMarkup([[stats.finished_books, "Marked finished"], [stats.in_progress_books, "In progress"], [stats.votes_cast, "Votes cast"], [stats.proposals_made, "Books proposed"]])}</section><section class="stats-panel"><p class="eyebrow">Recently</p><h2>Your activity</h2><div class="stats-timeline">${stats.recent.length ? stats.recent.map((item) => `<article><small>${escapeHtml(formatTimestamp(item.occurred_at))}</small><p><strong>${escapeHtml(item.label)}</strong>${item.detail ? `<br><small>${escapeHtml(item.detail)}</small>` : ""}</p></article>`).join("") : '<p class="muted">Ratings, votes, proposals, and progress updates will appear here.</p>'}</div></section></div>`;
};

const renderClubStats = (stats) => {
  participantState.clubStats = stats;
  $("#club-stats-content").innerHTML = `${statCardsMarkup([
    [stats.books_completed, "Books completed"],
    [stats.meetings_held, "Meetings held"],
    [stats.pages_read_together.toLocaleString(), "Pages read together"],
    [stats.average_rating == null ? "—" : `${stats.average_rating}★`, `Club average · ${stats.rating_count} ratings`],
  ])}<div class="stats-layout"><section class="stats-panel"><p class="eyebrow">The shelf</p><h2>${stats.shelf_total} club books</h2>${statBarsMarkup([{ label: "Completed", value: stats.shelf_completed }, { label: "Current", value: stats.shelf_current }, { label: "Coming up", value: stats.shelf_up_next }], "Books will appear as the facilitator builds the shelf.")}</section><section class="stats-panel"><p class="eyebrow">Favourite territory</p><h2>Top genres</h2>${statBarsMarkup(stats.favourite_genres, "Genres have not been added to the club books yet.")}</section><section class="stats-panel"><p class="eyebrow">Reading commitment</p><h2>Book-length mix</h2>${statBarsMarkup(stats.page_length_mix, "Page counts have not been added yet.")}</section><section class="stats-panel"><p class="eyebrow">Shared reactions</p><h2>Rating distribution</h2>${statBarsMarkup(stats.rating_distribution, "The club has not rated a book yet.")}</section><section class="stats-panel wide"><p class="eyebrow">Club favourites</p><h2>Highest-rated books</h2><div class="top-books-grid">${stats.top_rated_books.length ? stats.top_rated_books.map((book) => `<article class="top-book" data-open-book="${book.book_id}" role="button" tabindex="0"><img src="${escapeHtml(book.cover_image_url || "/static/assets/library-tools-logo-classic.svg?v=1")}" alt="" /><div><strong>${escapeHtml(book.title)}</strong><p>${escapeHtml(book.author)}</p><b>${book.average_rating}★ · ${book.rating_count} rating${book.rating_count === 1 ? "" : "s"}</b></div></article>`).join("") : '<p class="muted">Top-rated books will appear once members share their ratings.</p>'}</div></section><section class="stats-panel wide"><p class="eyebrow">Across meetings</p><h2>Attendance journey</h2><div class="stats-timeline">${stats.attendance_trend.length ? stats.attendance_trend.map((meeting) => `<article data-open-book="${meeting.book_id}" role="button" tabindex="0"><small>${escapeHtml(formatDate(meeting.meeting_date))}</small><p><strong>${escapeHtml(meeting.title)}</strong></p><b>${meeting.attendance_count} of ${meeting.roster_count}</b></article>`).join("") : '<p class="muted">Completed meetings will build the club timeline.</p>'}</div></section></div>`;
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
    ? members.map((member) => `<article class="directory-card"><div class="discussion-author">${avatarMarkup(member)}<div><strong>${escapeHtml(member.name)}${member.is_self ? " (you)" : ""}</strong>${member.bio ? `<p class="muted">${escapeHtml(member.bio)}</p>` : '<p class="muted">No introduction yet.</p>'}</div></div></article>`).join("")
    : '<p class="muted">No members have joined the directory yet.</p>';
};

const loadDirectory = async () => renderDirectory(await request("/participant/members"));

const readingPaceCopy = (detail, progress) => {
  const total = detail.book.page_count;
  const current = Number(progress?.current_page || 0);
  if (!total) return "Add a page count to this book to calculate a reading pace.";
  if (!detail.meeting_date) return `${Math.max(0, total - current)} pages remaining. Schedule a meeting to calculate a pace.`;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const target = new Date(`${detail.meeting_date}T00:00:00`);
  const days = Math.max(1, Math.ceil((target - today) / 86400000));
  const remaining = Math.max(0, total - current);
  if (!remaining) return "You’ve reached the end — nicely done.";
  return `${remaining} pages remaining · ${days} day${days === 1 ? "" : "s"} · ${Math.ceil(remaining / days)} pages per day or ${Math.ceil((remaining * 7) / days)} pages per week`;
};

const bookJourneyNeighbors = (bookId) => {
  const books = [
    ...participantState.library.previously_read,
    ...participantState.library.current,
    ...participantState.library.up_next,
  ];
  const ids = [...new Set(books.map((book) => book.id))];
  const index = ids.indexOf(Number(bookId));
  return { previous: index > 0 ? ids[index - 1] : null, next: index >= 0 && index < ids.length - 1 ? ids[index + 1] : null };
};

const sessionArchiveMarkup = (detail) => {
  const sessions = detail.sessions.filter((session) => session.status === "completed");
  if (!sessions.length) return "";
  return `<section class="book-hub-panel book-session-panel" data-book-hub-panel="session"><div class="book-panel-heading"><div><p class="eyebrow">Previous session</p><h3>${sessions.length === 1 ? "The club’s conversation" : `${sessions.length} club sessions`}</h3></div><p>A participant-safe recap with shared totals and facilitator discussion notes.</p></div><div class="session-archive-stats"><article class="portal-stat-card"><strong>${sessions.length}</strong><span>Session${sessions.length === 1 ? "" : "s"}</span></article><article class="portal-stat-card"><strong>${detail.total_attendance}</strong><span>Total attendance</span></article><article class="portal-stat-card"><strong>${detail.reading_impact_pages.toLocaleString()}</strong><span>Pages read together</span></article><article class="portal-stat-card"><strong>${detail.shared_progress.length}</strong><span>Shared progress updates</span></article></div><div class="session-list">${sessions.map((session) => `<article class="session-summary-card"><header><div><h4>${escapeHtml(formatDate(session.meeting_date))}</h4><small>${escapeHtml([session.meeting_time, session.location].filter(Boolean).join(" · ") || "Meeting details not recorded")}</small></div><strong>${session.attendance_count} of ${session.roster_count} attended</strong></header>${session.discussion_notes ? `<p>${escapeHtml(session.discussion_notes)}</p>` : '<p class="muted">No discussion recap was added.</p>'}</article>`).join("")}</div></section>`;
};

const discussionMarkup = (posts) => {
  const roots = posts.filter((post) => post.parent_id == null);
  const replies = posts.filter((post) => post.parent_id != null);
  const postMarkup = (post, reply = false) => `<article class="${reply ? "discussion-reply" : "discussion-thread"}"><div class="discussion-author">${avatarMarkup(post.author)}<div><strong>${escapeHtml(post.author.name)}</strong><small class="user-meta">${escapeHtml(formatTimestamp(post.created_at))}</small></div></div><p class="discussion-body${post.spoiler ? " spoiler-text" : ""}"${post.spoiler ? ` data-reveal-spoiler="true" data-body="${escapeHtml(post.body)}"` : ""}>${post.spoiler ? "Spoiler — click to reveal" : escapeHtml(post.body)}</p><div class="post-meeting-actions"><button class="quiet-button reaction-button${post.reacted_by_me ? " is-active" : ""}" type="button" data-react-post="${post.id}">♥ ${post.reaction_count}</button>${reply ? "" : `<button class="quiet-button" type="button" data-detail-reply="${post.id}">Reply</button>`}${post.author.is_self ? `<button class="quiet-button" type="button" data-detail-delete-post="${post.id}">Delete</button>` : ""}</div>${reply ? "" : `<form class="reply-form" data-detail-reply-form="${post.id}" hidden><textarea rows="2" maxlength="4000" placeholder="Write a reply"></textarea><label><input type="checkbox" name="spoiler" /> Contains spoilers</label><button class="secondary-button" type="submit">Post reply</button></form><div class="discussion-replies">${replies.filter((item) => item.parent_id === post.id).map((item) => postMarkup(item, true)).join("")}</div>`}</article>`;
  return roots.length ? roots.map((post) => postMarkup(post)).join("") : '<p class="muted">No posts yet. Start the conversation.</p>';
};

const renderBookPage = ({ detail, ratings, progress, posts }) => {
  const book = detail.book;
  const mine = ratings.ratings.find((item) => item.participant_id === ratingsState.participantId);
  const tab = participantState.bookHubTab;
  const hasSession = detail.sessions.some((session) => session.status === "completed");
  const isCurrentBook = participantState.upcomingMeeting?.meeting?.book?.id === book.id;
  const neighbors = bookJourneyNeighbors(book.id);
  const distribution = [5, 4.5, 4, 3.5, 3, 2.5, 2, 1.5, 1]
    .filter((score) => ratings.ratings.some((item) => item.rating === score))
    .map((score) => `${score}★ ${ratings.ratings.filter((item) => item.rating === score).length}`)
    .join(" · ") || "No ratings yet";
  const bookActivity = participantState.clubActivity.filter((item) => item.book.id === book.id && item.kind !== "discussion");
  const activityMarkup = bookActivity.length
    ? `<div class="conversation-updates">${bookActivity.slice(0, 6).map((item) => `<article class="conversation-update">${avatarMarkup(item.actor)}<div><p><strong>${escapeHtml(item.actor.name)}</strong> ${item.kind === "rating" ? "rated this book" : "updated their reading progress"}${item.detail ? ` · ${escapeHtml(item.detail)}` : ""}</p><small>${escapeHtml(formatTimestamp(item.created_at))}</small></div></article>`).join("")}</div>`
    : "";
  const tabs = [...(hasSession ? [["session", "Session recap"]] : []), ["conversation","Conversation"],["ratings","Ratings"],["progress","Reading progress"]];
  $("#book-page-content").innerHTML = `<div class="book-page-hero"><img class="book-page-cover" src="${escapeHtml(book.cover_image_url || "/static/assets/library-tools-logo-classic.svg?v=1")}" alt="" /><div class="book-page-intro"><p class="eyebrow">${escapeHtml(book.author)}</p><h2>${escapeHtml(book.title)}</h2><p class="book-page-summary">${escapeHtml(book.description || "No description has been added yet.")}</p><div class="book-quick-meta"><span>${book.page_count ? `${book.page_count} pages` : "Page count unavailable"}</span><span>${ratings.average != null ? `${ratings.average}★ from ${ratings.count}` : "No ratings yet"}</span>${hasSession ? "<span>Previously read</span>" : ""}</div><div class="book-primary-actions">${neighbors.previous ? `<button class="secondary-button" type="button" data-open-book="${neighbors.previous}">← Previous book</button>` : ""}${neighbors.next ? `<button class="secondary-button" type="button" data-open-book="${neighbors.next}">Next book →</button>` : ""}${book.catalogue_url ? `<a class="secondary-button" href="${escapeHtml(book.catalogue_url)}" target="_blank" rel="noopener">Find in catalogue ↗</a>` : ""}</div>${isCurrentBook ? meetingHeroMarkup(participantState.upcomingMeeting) : ""}</div></div>
    <div class="book-hub-tabs" role="tablist" aria-label="Book sections">${tabs.map(([value,label]) => `<button type="button" role="tab" data-book-hub-tab="${value}" aria-selected="${tab === value}" class="${tab === value ? "active" : ""}">${label}${value === "conversation" && posts.length ? ` <span>${posts.length}</span>` : ""}</button>`).join("")}</div>
    ${sessionArchiveMarkup(detail)}
    <section class="book-hub-panel" data-book-hub-panel="conversation"${tab === "conversation" ? "" : " hidden"}><div class="book-panel-heading"><div><p class="eyebrow">Club conversation</p><h3>Read and respond</h3></div><p>Progress updates, ratings, and discussion in one place.</p></div>${activityMarkup}<form class="discussion-compose conversation-composer" id="detail-discussion-form"><textarea rows="3" maxlength="4000" placeholder="Share a thought or question with your club…"></textarea><div class="composer-actions"><label><input type="checkbox" name="spoiler" /> Contains spoilers</label><button class="primary-button" type="submit">Post</button></div></form><div id="detail-discussion-list">${discussionMarkup(posts)}</div></section>
    <section class="book-hub-panel" data-book-hub-panel="ratings"${tab === "ratings" ? "" : " hidden"}><div class="book-panel-heading"><div><p class="eyebrow">Club ratings</p><h3>${ratings.average != null ? `${ratings.average}★ average` : "No ratings yet"}</h3></div><p>${distribution}</p></div><div class="ratings-calm-layout"><div class="your-rating-editor"><p class="eyebrow">Your rating</p><output class="rating-value" id="detail-rating-value">${mine?.rating || 3}★</output><input class="rating-range" id="detail-rating" type="range" min="1" max="5" step="0.5" value="${mine?.rating || 3}" aria-label="Rating in half-star increments" /><textarea id="detail-review" rows="3" maxlength="4000" placeholder="Add an optional review">${escapeHtml(mine?.review_text || "")}</textarea><button class="primary-button" id="save-detail-rating" type="button">${mine ? "Update rating" : "Save rating"}</button></div><div class="club-review-list">${ratings.ratings.length ? ratings.ratings.map((item) => `<article><p><strong>${escapeHtml(item.participant_name)}</strong><span>${item.rating}★</span></p>${item.review_text ? `<p>${escapeHtml(item.review_text)}</p>` : ""}</article>`).join("") : '<p class="muted">Be the first to rate this book.</p>'}</div></div></section>
    <section class="book-hub-panel" data-book-hub-panel="progress"${tab === "progress" ? "" : " hidden"}><div class="book-panel-heading"><div><p class="eyebrow">Reading progress</p><h3>Stay on pace</h3></div><p>Private unless you choose to share it.</p></div><div class="progress-calm-layout"><form class="progress-form" id="detail-progress-form"><label>Status<select name="status"><option value="not_started"${progress.status === "not_started" ? " selected" : ""}>Not started</option><option value="reading"${progress.status === "reading" ? " selected" : ""}>Reading</option><option value="finished"${progress.status === "finished" ? " selected" : ""}>Finished</option></select></label><div class="progress-form-row"><label>Current page<input name="current_page" type="number" min="0" ${book.page_count ? `max="${book.page_count}"` : ""} value="${progress.current_page ?? 0}" /></label><label>Book club day<input value="${detail.meeting_date ? escapeHtml(formatDate(detail.meeting_date)) : "Not scheduled"}" disabled /></label></div><div class="pace-result" id="pace-result">${escapeHtml(readingPaceCopy(detail, progress))}</div><label class="preference-option"><input name="shared_with_club" type="checkbox"${progress.shared_with_club ? " checked" : ""} /><span><strong>Share my progress</strong><small>Members can see your status and current page.</small></span></label><button class="primary-button" type="submit">Save progress</button></form><div class="shared-progress-list"><p class="eyebrow">Reading together</p>${detail.shared_progress.length ? detail.shared_progress.map((item) => `<div class="shared-progress-item"><strong>${escapeHtml(item.member.name)}</strong><span>${escapeHtml(progressLabels[item.status] || item.status)}${item.current_page != null ? ` · page ${item.current_page}` : ""}</span></div>`).join("") : '<p class="muted">No one has shared progress yet.</p>'}</div></div></section>
    <details class="book-about"><summary>About this book</summary><p>${escapeHtml(book.description || "No description has been added yet.")}</p><p class="muted">${book.page_count ? `${book.page_count} pages · ` : ""}${escapeHtml(book.genres || "")}</p></details>`;
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
  if (event.target.id === "detail-rating") $("#detail-rating-value").textContent = `${event.target.value}★`;
  if (event.target.name === "current_page" && $("#pace-result")) {
    $("#pace-result").textContent = readingPaceCopy(participantState.activeBookDetail, { current_page: Number(event.target.value || 0) });
  }
});
$("#book-page-content").addEventListener("click", async (event) => {
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
    if (event.target.id === "save-detail-rating") await request(`/participant/books/${participantState.activeBookId}/rating`, { method: "PUT", body: JSON.stringify({ rating: Number($("#detail-rating").value), review_text: $("#detail-review").value.trim() || null }) });
    else if (react) await request(`/participant/discussion/${react.dataset.reactPost}/reaction`, { method: "PUT" });
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

const openProfileDialog = async () => {
  try {
    participantState.profile = participantState.profile || await request("/participant/profile");
    const form = $("#profile-form");
    form.elements.name.value = participantState.profile.name;
    form.elements.avatar_url.value = participantState.profile.avatar_url || "";
    form.elements.bio.value = participantState.profile.bio || "";
    form.elements.directory_visible.checked = participantState.profile.directory_visible;
    $("#profile-error").textContent = "";
    $("#profile-dialog").showModal();
  } catch (error) { toast(error.message); }
};

$("#profile-settings").addEventListener("click", openProfileDialog);
$("#edit-directory-profile").addEventListener("click", openProfileDialog);
$("#close-profile-dialog").addEventListener("click", () => $("#profile-dialog").close());
$("#profile-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
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
    $("#welcome-heading").textContent = `Welcome, ${capitalizeFirst(participantState.profile.name)}`;
    await loadDirectory();
    toast("Profile saved.");
  } catch (error) { $("#profile-error").textContent = error.message; }
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
  const data = Object.fromEntries(["announcements", "polls", "meeting_reminders", "discussion_replies"].map((name) => [name, form.elements[name].checked]));
  data.delivery_frequency = form.elements.delivery_frequency.value;
  try {
    notificationPreferences = await request("/participant/notification-preferences", { method: "PUT", body: JSON.stringify(data) });
    $("#notification-dialog").close();
    toast("Notification preferences saved.");
  } catch (error) { $("#notification-error").textContent = error.message; }
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
  } catch {
    location.href = "/";
  }
})();
