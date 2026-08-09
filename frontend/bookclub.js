const state = {
  user: null,
  clubs: [],
  club: null,
  view: "meetings",
  members: [],
  books: [],
  meetings: [],
  meetingId: null,
  roster: [],
  viewingEdit: true,
  dayOfMode: false,
  discussionNotesDirty: false,
  templates: [],
  templateKey: null,
  participation: [],
  memberSort: "name",
  bookSort: "title-asc",
  bookDisplay: "list",
  bookUnscheduledOnly: false,
  bookDetailId: null,
  memberQuery: "",
  meetingQuery: "",
  bookQuery: "",
};
const dashboardActionParams = new URLSearchParams(window.location.search);
let pendingDashboardAction = dashboardActionParams.get("action");
const pendingDashboardClubId = dashboardActionParams.get("club")
  ? Number(dashboardActionParams.get("club"))
  : null;
const pendingDashboardMemberId = dashboardActionParams.get("member")
  ? Number(dashboardActionParams.get("member"))
  : null;
const pendingDashboardStage = dashboardActionParams.get("stage");

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const loginDialog = $("#login-dialog");
const clubDialog = $("#club-dialog");
const toast = $("#toast");
const accountMenu = $("#account-menu");

const capitalizeFirst = (value = "") => {
  const characters = Array.from(String(value));
  return characters.length
    ? characters[0].toLocaleUpperCase() + characters.slice(1).join("")
    : "";
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
    const detail = body.detail;
    const message =
      typeof detail === "string"
        ? detail
        : detail?.[0]?.msg || "Something went wrong.";
    const error = new Error(message);
    error.status = response.status;
    if (response.status === 401) showLogin();
    throw error;
  }
  return body;
};

const showToast = (message) => {
  toast.textContent = message;
  toast.classList.add("show");
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => toast.classList.remove("show"), 2600);
};

const showLogin = () => {
  state.user = null;
  accountMenu.open = false;
  if (!loginDialog.open) loginDialog.showModal();
};

const applyUser = (user) => {
  state.user = user;
  $("#user-badge").textContent = user.role === "admin" ? "Administrator" : "Member";
  $("#account-menu-name").textContent = capitalizeFirst(user.name);
  $("#account-menu-username").textContent = `@${user.username}`;
  document.querySelectorAll("[data-platform-admin-only]").forEach((element) => {
    element.hidden = user.role !== "admin";
  });
};

const applyClub = (club) => {
  state.club = club;
  $("#sidebar-club-name").textContent = club.name;
  $("#switch-club").textContent = club.name;
  const publicLink = $("#public-club-link");
  publicLink.hidden = !club.public;
  publicLink.href = `/clubs/${encodeURIComponent(club.slug)}`;
};

const populateClubSettingsForm = () => {
  const club = state.club;
  if (!club) return;
  const form = $("#club-settings-form");
  form.reset();
  form.elements.name.value = club.name || "";
  form.elements.description.value = club.description || "";
  form.elements.organizer_name.value = club.organizer_name || "";
  form.elements.organizer_branch.value = club.organizer_branch || "";
  form.elements.video_call_url.value = club.video_call_url || "";
  form.elements.public.value = String(club.public ?? true);
  $("#club-settings-error").textContent = "";
};

const renderClubChoices = () => {
  $("#club-choice-list").innerHTML = state.clubs.length
    ? state.clubs.map((club) => `<button class="club-choice" type="button" data-club-id="${club.id}"><strong>${escapeHtml(club.name)}</strong><span>Open →</span></button>`).join("")
    : '<p class="empty-inline">You do not have a book club yet.</p>';
};

const showClubPicker = () => {
  renderClubChoices();
  if (!clubDialog.open) clubDialog.showModal();
};

const finishDashboardAction = () => {
  pendingDashboardAction = null;
  const url = new URL(window.location.href);
  ["action", "club", "member", "stage"].forEach((key) => url.searchParams.delete(key));
  window.history.replaceState({}, "", `${url.pathname}${url.search}${url.hash}`);
};

const runDashboardAction = async () => {
  if (!pendingDashboardAction || !state.club) return;
  const action = pendingDashboardAction;
  const memberId = pendingDashboardMemberId;
  const stage = pendingDashboardStage;
  finishDashboardAction();
  if (action === "add-member") {
    await setView("members");
    openMemberDialog();
  } else if (action === "add-book") {
    await setView("books");
    openBookDialog();
  } else if (action === "view-meetings") {
    await setView("meetings");
  } else if (action === "view-books") {
    await setView("books");
  } else if (action === "view-members") {
    await setView("members");
  } else if (action === "view-settings") {
    await setView("club-settings");
  } else if (action === "followup" && memberId && stage) {
    await jumpToPendingMeeting(memberId, stage);
  }
};

const chooseClub = async (clubId) => {
  const club = await request(`/bookclub/clubs/${clubId}/select`, { method: "POST" });
  applyClub(club);
  clubDialog.close();
  await loadCoreData();
  await setView(state.meetingId ? "meeting" : "meetings");
  await runDashboardAction();
};

const loadClubs = async () => {
  state.clubs = await request("/bookclub/clubs");
  if (!state.clubs.length) return showClubPicker();
  if (
    pendingDashboardClubId &&
    state.clubs.some((club) => club.id === pendingDashboardClubId)
  ) {
    return chooseClub(pendingDashboardClubId);
  }
  let selected = null;
  try {
    selected = await request("/bookclub/clubs/selected");
  } catch (error) {
    if (error.status !== 404) throw error;
  }
  if (selected && state.clubs.some((club) => club.id === selected.id)) {
    applyClub(selected);
    await loadCoreData();
    await setView(state.meetingId ? "meeting" : "meetings");
    await runDashboardAction();
  } else if (state.clubs.length === 1) {
    await chooseClub(state.clubs[0].id);
  } else {
    showClubPicker();
  }
};

const today = () => {
  const value = new Date();
  value.setMinutes(value.getMinutes() - value.getTimezoneOffset());
  return value.toISOString().slice(0, 10);
};

const formatDate = (value) => {
  if (!value) return "Date not set";
  return new Intl.DateTimeFormat("en-CA", {
    month: "long",
    day: "numeric",
    year: "numeric",
  }).format(new Date(`${value}T12:00:00`));
};

const initials = (name) =>
  name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((word) => word[0])
    .join("")
    .toUpperCase();

const currentMeeting = () =>
  state.meetings.find((meeting) => meeting.id === state.meetingId) || null;

const MEETING_STATUS_LABELS = {
  planned: "Planned",
  in_progress: "In progress",
  completed: "Completed",
};

// "in_progress" is never stored — it's computed from the meeting's time
// window (starts_at/ends_at, server-computed from meeting_time + duration,
// null when meeting_time doesn't parse). "completed" is the one manual
// stored state besides the "planned" default.
const effectiveMeetingStatus = (meeting) => {
  if (!meeting) return "planned";
  if (meeting.status === "completed") return "completed";
  if (meeting.starts_at && meeting.ends_at) {
    const now = new Date();
    if (now >= new Date(meeting.starts_at) && now < new Date(meeting.ends_at)) {
      return "in_progress";
    }
  }
  return "planned";
};

const meetingStatusLabel = (meeting) =>
  MEETING_STATUS_LABELS[effectiveMeetingStatus(meeting)];

const chooseDefaultMeeting = () => {
  if (!state.meetings.length) return null;
  const upcoming = state.meetings
    .filter((meeting) => meeting.meeting_date >= today())
    .sort((a, b) => a.meeting_date.localeCompare(b.meeting_date));
  return upcoming[0]?.id || state.meetings[0].id;
};

// Lets staff pick a previously-used branch again instead of retyping it —
// native <datalist> autocomplete fed by the distinct branches already on
// file, no backend endpoint needed.
const renderBranchSuggestions = () => {
  const branches = [...new Set(state.members.map((member) => member.destination_branch).filter(Boolean))].sort();
  $("#branch-suggestions").innerHTML = branches
    .map((branch) => `<option value="${escapeHtml(branch)}"></option>`)
    .join("");
};

const loadCoreData = async () => {
  const [members, books, meetings, participation] = await Promise.all([
    request("/bookclub/members?limit=500"),
    request("/bookclub/books?limit=500"),
    request("/bookclub/meetings?limit=500"),
    request("/bookclub/members/participation-summary"),
  ]);
  state.members = members;
  state.books = books;
  state.meetings = meetings;
  state.participation = participation;
  renderBranchSuggestions();
  if (!state.meetings.some((meeting) => meeting.id === state.meetingId)) {
    state.meetingId = chooseDefaultMeeting();
  }
  renderMeetings();
  renderBooks();
  renderMembers();
  await loadSelectedMeeting();
};

const loadSelectedMeeting = async () => {
  state.discussionNotesDirty = false;
  // Default landing view for this meeting: archive summary if it's been
  // archived, the normal workspace otherwise. Whichever the user then
  // switches to (via Archive/Edit session) sticks until the next meeting.
  state.viewingEdit = !currentMeeting()?.archived_at;
  if (!state.meetingId) {
    state.roster = [];
    renderMeetingView();
    return;
  }
  state.roster = await request(`/bookclub/meetings/${state.meetingId}/roster`);
  renderMeetingView();
};

const renderMeetings = () => {
  const query = state.meetingQuery.trim().toLowerCase();
  const meetings = state.meetings.filter((meeting) =>
    [
      meeting.book.title,
      meeting.book.author,
      meeting.meeting_date,
      meeting.location,
    ]
      .filter(Boolean)
      .join(" ")
      .toLowerCase()
      .includes(query),
  );
  const upcoming = meetings
    .filter((meeting) => meeting.meeting_date >= today())
    .sort((a, b) => a.meeting_date.localeCompare(b.meeting_date));
  const past = meetings
    .filter((meeting) => meeting.meeting_date < today())
    .sort((a, b) => b.meeting_date.localeCompare(a.meeting_date));
  const list = $("#meeting-list");
  $("#meeting-count").textContent = query
    ? `${meetings.length} matching`
    : `${upcoming.length} upcoming · ${past.length} past`;
  if (!meetings.length) {
    list.innerHTML = `<div class="empty-collection"><span>◫</span><h2>${query ? "No matching meetings" : "No meetings yet"}</h2><p>${query ? "Try a different search." : "Add the first meeting after creating a book for the club."}</p>${query ? "" : '<button class="primary-button" type="button" data-add-meeting><svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12h14" /><path d="M12 5v14" /></svg> Add meeting</button>'}</div>`;
    return;
  }
  const meetingDateParts = (meeting) => {
    const date = new Date(`${meeting.meeting_date}T12:00:00`);
    return {
      month: new Intl.DateTimeFormat("en-CA", { month: "short" }).format(date),
      day: new Intl.DateTimeFormat("en-CA", { day: "numeric" }).format(date),
      year: new Intl.DateTimeFormat("en-CA", { year: "numeric" }).format(date),
    };
  };
  const nextUpcomingId = upcoming[0]?.id;
  const upcomingCards = upcoming.map((meeting) => {
    const date = meetingDateParts(meeting);
    const cover = safeImageUrl(meeting.book.cover_image_url);
    const featured = meeting.id === nextUpcomingId;
    const effectiveStatus = effectiveMeetingStatus(meeting);
    const statusLabel = effectiveStatus === "planned"
      ? featured ? "Next meeting" : "Coming up"
      : meetingStatusLabel(meeting);
    return `<button class="upcoming-meeting-card ${featured ? "next-meeting-card" : ""} status-${escapeHtml(effectiveStatus)}" type="button" data-open-meeting="${meeting.id}">
      <div class="meeting-card-cover">${cover ? `<img src="${escapeHtml(cover)}" alt="" />` : escapeHtml(initials(meeting.book.title))}</div>
      <div class="upcoming-meeting-copy">
        <span class="meeting-status-label">${escapeHtml(statusLabel)}</span>
        <p class="meeting-calendar-date"><strong>${escapeHtml(date.day)}</strong><span>${escapeHtml(date.month)} ${escapeHtml(date.year)}</span></p>
        <h2>${escapeHtml(meeting.book.title)}</h2>
        <p class="meeting-card-author">by ${escapeHtml(meeting.book.author)}</p>
        <div class="meeting-card-meta">${meeting.meeting_time ? `<span>◷ ${escapeHtml(meeting.meeting_time)}</span>` : ""}${meeting.location ? `<span>⌖ ${escapeHtml(meeting.location)}</span>` : ""}</div>
      </div>
      <span class="meeting-card-arrow" aria-hidden="true">→</span>
    </button>`;
  }).join("");
  const pastCards = past.map((meeting) => {
    const date = meetingDateParts(meeting);
    const cover = safeImageUrl(meeting.book.cover_image_url);
    return `<button class="past-meeting-card status-${escapeHtml(effectiveMeetingStatus(meeting))}" type="button" data-open-meeting="${meeting.id}">
      <div class="past-meeting-cover">${cover ? `<img src="${escapeHtml(cover)}" alt="" />` : escapeHtml(initials(meeting.book.title))}</div>
      <div><span class="past-meeting-date">${escapeHtml(date.month)} ${escapeHtml(date.day)}, ${escapeHtml(date.year)} · ${escapeHtml(meetingStatusLabel(meeting))}</span><h3>${escapeHtml(meeting.book.title)}</h3><p>by ${escapeHtml(meeting.book.author)}</p></div>
      <span aria-hidden="true">→</span>
    </button>`;
  }).join("");
  const upcomingSection = upcoming.length
    ? `<section class="meeting-section upcoming-meetings"><header><div><p class="eyebrow"><span></span> On the horizon</p><h2>Upcoming book clubs</h2></div><span class="section-count">${upcoming.length}</span></header><div class="upcoming-meeting-grid">${upcomingCards}</div></section>`
    : query
      ? ""
      : '<section class="meeting-section upcoming-meetings"><header><div><p class="eyebrow"><span></span> On the horizon</p><h2>Upcoming book clubs</h2></div><span class="section-count">0</span></header><div class="meeting-section-empty"><span>◫</span><div><strong>Nothing scheduled yet</strong><p>Add the next book and gathering when the club is ready.</p></div><button class="secondary-button" type="button" data-add-meeting>Plan a meeting</button></div></section>';
  const pastSection = past.length
    ? `<section class="meeting-section past-meetings"><header><div><p class="eyebrow"><span></span> The reading archive</p><h2>Past meetings</h2></div><span class="section-count">${past.length}</span></header><div class="past-meeting-grid">${pastCards}</div></section>`
    : query
      ? ""
      : '<section class="meeting-section past-meetings"><header><div><p class="eyebrow"><span></span> The reading archive</p><h2>Past meetings</h2></div><span class="section-count">0</span></header><div class="meeting-section-empty quiet"><span>◇</span><div><strong>Your archive starts here</strong><p>Completed meetings will collect here automatically.</p></div></div></section>';
  list.innerHTML = upcomingSection + pastSection;
};

const safeImageUrl = (value) => {
  if (!value) return "";
  try {
    const url = new URL(value);
    return ["http:", "https:"].includes(url.protocol) ? url.href : "";
  } catch {
    return "";
  }
};

const scheduledBookIds = () => new Set(state.meetings.map((meeting) => meeting.book_id));

const renderBookStats = () => {
  const books = state.books;
  const completedMeetingBookIds = new Set(state.meetings
    .filter((meeting) => meeting.meeting_date <= today())
    .map((meeting) => meeting.book_id));
  const upcomingMeetingBookIds = new Set(state.meetings
    .filter((meeting) => meeting.meeting_date > today())
    .map((meeting) => meeting.book_id));
  $("#book-stat-total").textContent = books.length;
  const meetingsHeld = state.meetings.filter(
    (meeting) => meeting.meeting_date <= today(),
  ).length;
  $("#book-stat-meetings").textContent = meetingsHeld;
  const withPages = books.filter((book) => book.page_count);
  const totalPages = withPages.reduce((sum, book) => sum + book.page_count, 0);
  $("#book-stat-pages").textContent = totalPages ? totalPages.toLocaleString() : "—";
  const avgPages = withPages.length
    ? Math.round(totalPages / withPages.length)
    : null;
  $("#book-stat-avg-pages").textContent = avgPages ?? "—";
  $("#book-pages-known").textContent = withPages.length
    ? `${withPages.length} measured`
    : "No data";

  const lengthGroups = [
    { label: "Quick reads", note: "Under 300 pages", count: withPages.filter((book) => book.page_count < 300).length },
    { label: "Middle distance", note: "300–499 pages", count: withPages.filter((book) => book.page_count >= 300 && book.page_count < 500).length },
    { label: "Long reads", note: "500+ pages", count: withPages.filter((book) => book.page_count >= 500).length },
  ];
  $("#book-length-breakdown").innerHTML = withPages.length
    ? lengthGroups.map((group) => {
      const percent = Math.round((group.count / withPages.length) * 100);
      return `<div class="book-bar-row"><div><strong>${escapeHtml(group.label)}</strong><span>${escapeHtml(group.note)}</span></div><div class="book-bar-track" aria-label="${escapeHtml(group.label)}: ${group.count} books"><span style="width:${percent}%"></span></div><b>${group.count}</b></div>`;
    }).join("")
    : '<p class="insight-empty">Add page counts to see the collection’s reading commitment.</p>';

  const genreCounts = new Map();
  books.forEach((book) => {
    (book.genres || "")
      .split(",")
      .map((genre) => genre.trim())
      .filter(Boolean)
      .forEach((genre) => genreCounts.set(genre, (genreCounts.get(genre) || 0) + 1));
  });
  const topGenres = [...genreCounts.entries()]
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .slice(0, 4);
  $("#book-genre-count").textContent = genreCounts.size
    ? `${genreCounts.size} ${genreCounts.size === 1 ? "genre" : "genres"}`
    : "No data";
  const topGenreCount = topGenres[0]?.[1] || 0;
  $("#book-genre-breakdown").innerHTML = topGenres.length
    ? topGenres.map(([genre, count]) => `<div class="book-bar-row"><div><strong>${escapeHtml(genre)}</strong><span>${count} ${count === 1 ? "title" : "titles"}</span></div><div class="book-bar-track" aria-label="${escapeHtml(genre)}: ${count} titles"><span style="width:${Math.round((count / topGenreCount) * 100)}%"></span></div><b>${count}</b></div>`).join("")
    : '<p class="insight-empty">Add genres to reveal the club’s favourite territory.</p>';

  const readCount = books.filter((book) => book.is_past_selection || completedMeetingBookIds.has(book.id)).length;
  const upcomingCount = books.filter((book) => !book.is_past_selection && !completedMeetingBookIds.has(book.id) && upcomingMeetingBookIds.has(book.id)).length;
  const unscheduledCount = Math.max(books.length - readCount - upcomingCount, 0);
  const readDegrees = books.length ? (readCount / books.length) * 360 : 0;
  const upcomingDegrees = books.length ? (upcomingCount / books.length) * 360 : 0;
  const ring = $("#book-status-ring");
  ring.style.background = books.length
    ? `conic-gradient(var(--forest-soft) 0deg ${readDegrees}deg, var(--gold) ${readDegrees}deg ${readDegrees + upcomingDegrees}deg, rgba(110,157,154,.34) ${readDegrees + upcomingDegrees}deg 360deg)`
    : "rgba(24,59,51,.08)";
  ring.setAttribute("aria-label", `${readCount} read, ${upcomingCount} scheduled, ${unscheduledCount} unscheduled`);
  $("#book-status-center").textContent = books.length;
  $("#book-status-legend").innerHTML = [
    ["Read", readCount, "read"],
    ["Coming up", upcomingCount, "upcoming"],
    ["Unscheduled", unscheduledCount, "unscheduled"],
  ].map(([label, count, className]) => `<div><dt><i class="${className}"></i>${label}</dt><dd>${count}</dd></div>`).join("");

  const datedBooks = books.filter((book) => book.publication_date);
  const oldestYear = datedBooks.length ? Math.min(...datedBooks.map((book) => Number(book.publication_date.slice(0, 4)))) : null;
  const newestYear = datedBooks.length ? Math.max(...datedBooks.map((book) => Number(book.publication_date.slice(0, 4)))) : null;
  $("#book-era-note").textContent = oldestYear
    ? oldestYear === newestYear
      ? `The dated shelf is rooted in ${oldestYear}.`
      : `The shelf spans ${newestYear - oldestYear} years, from ${oldestYear} to ${newestYear}.`
    : "Add publication dates to see the shelf across time.";
  $("#book-insights-summary").textContent = books.length
    ? `${readCount} read · ${upcomingCount} coming up · ${unscheduledCount} waiting on the shelf`
    : "A living portrait of the club shelf.";
};

const compareNullableNumbers = (left, right, direction) => {
  const leftMissing = left === null || left === undefined || Number.isNaN(left);
  const rightMissing = right === null || right === undefined || Number.isNaN(right);
  if (leftMissing && rightMissing) return 0;
  if (leftMissing) return 1;
  if (rightMissing) return -1;
  return direction * (left - right);
};

const sortBooks = (books) => [...books].sort((left, right) => {
  const titleFallback = left.title.localeCompare(right.title, undefined, { sensitivity: "base" });
  switch (state.bookSort) {
    case "title-desc": return right.title.localeCompare(left.title, undefined, { sensitivity: "base" });
    case "pages-asc": return compareNullableNumbers(left.page_count, right.page_count, 1) || titleFallback;
    case "pages-desc": return compareNullableNumbers(left.page_count, right.page_count, -1) || titleFallback;
    case "year-asc": return compareNullableNumbers(left.publication_date ? Date.parse(left.publication_date) : null, right.publication_date ? Date.parse(right.publication_date) : null, 1) || titleFallback;
    case "year-desc": return compareNullableNumbers(left.publication_date ? Date.parse(left.publication_date) : null, right.publication_date ? Date.parse(right.publication_date) : null, -1) || titleFallback;
    case "author-asc": return left.author.localeCompare(right.author, undefined, { sensitivity: "base" }) || titleFallback;
    default: return titleFallback;
  }
});

const renderBooks = () => {
  const query = state.bookQuery.trim().toLowerCase();
  const scheduled = scheduledBookIds();
  let books = state.books.filter((book) =>
    [book.title, book.author, book.isbn, book.genres]
      .filter(Boolean)
      .join(" ")
      .toLowerCase()
      .includes(query),
  );
  if (state.bookUnscheduledOnly) {
    books = books.filter(
      (book) => !scheduled.has(book.id) && !book.is_past_selection,
    );
  }
  books = sortBooks(books);
  $("#book-count").textContent = books.length === state.books.length
    ? `${books.length} ${books.length === 1 ? "book" : "books"}`
    : `${books.length} of ${state.books.length} books`;
  renderBookStats();
  const list = $("#book-list");
  list.classList.toggle("display-list", state.bookDisplay === "list");
  list.classList.toggle("compact-grid", state.bookDisplay === "grid");
  $$('[data-book-display]').forEach((button) => {
    button.setAttribute("aria-pressed", String(button.dataset.bookDisplay === state.bookDisplay));
  });
  if (!books.length) {
    list.innerHTML = `<div class="empty-collection"><span>▥</span><h2>${query || state.bookUnscheduledOnly ? "No matching books" : "Your book list is empty"}</h2><p>${query || state.bookUnscheduledOnly ? "Try a different title, author, ISBN, or genre." : "Add the first title selected for the club."}</p>${query || state.bookUnscheduledOnly ? "" : '<button class="primary-button" id="empty-add-book" type="button"><svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12h14" /><path d="M12 5v14" /></svg> Add book</button>'}</div>`;
    return;
  }
  list.innerHTML = books
    .map((book) => {
      const cover = safeImageUrl(book.cover_image_url);
      const publicationYear = book.publication_date?.slice(0, 4);
      const unscheduled = !scheduled.has(book.id) && !book.is_past_selection;
      const statusBadge = book.is_past_selection
        ? '<span class="status-pill past-selection-badge">Past selection</span>'
        : unscheduled
          ? '<span class="status-pill unscheduled-badge">Not yet scheduled</span>'
          : "";
      return `<article class="book-card" data-open-book-detail="${book.id}" role="button" tabindex="0" aria-label="View details for ${escapeHtml(book.title)}">${statusBadge}<div class="book-cover">${cover ? `<img src="${escapeHtml(cover)}" alt="Cover of ${escapeHtml(book.title)}" loading="lazy" />` : escapeHtml(initials(book.title))}</div><div class="book-card-copy"><h2>${escapeHtml(book.title)}</h2><p class="book-author">${escapeHtml(book.author)}</p><p class="book-description">${escapeHtml(book.description || "No description has been added yet.")}</p><div class="book-meta">${publicationYear ? `<span>${escapeHtml(publicationYear)}</span>` : ""}${book.page_count ? `<span>${book.page_count} pages</span>` : ""}${book.genres ? `<span>${escapeHtml(book.genres)}</span>` : ""}</div><span class="book-details-cue">View book details <b>→</b></span></div><div class="book-card-actions"><button type="button" data-edit-book="${book.id}"><svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21.174 6.812a1 1 0 0 0-3.986-3.987L3.842 16.174a2 2 0 0 0-.5.83l-1.321 4.352a.5.5 0 0 0 .623.622l4.353-1.32a2 2 0 0 0 .83-.497z" /><path d="m15 5 4 4" /></svg> Edit</button><button class="danger-text" type="button" data-delete-book="${book.id}"><svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M10 11v6" /><path d="M14 11v6" /><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6" /><path d="M3 6h18" /><path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" /></svg> Delete</button></div></article>`;
    })
    .join("");
};

const bookTimelineIds = () => {
  const ids = [];
  [...state.meetings]
    .sort((left, right) => left.meeting_date.localeCompare(right.meeting_date) || left.id - right.id)
    .forEach((meeting) => {
      if (!ids.includes(meeting.book_id)) ids.push(meeting.book_id);
    });
  return ids;
};

const bookDetailNeighbors = (bookId) => {
  let ids = bookTimelineIds();
  if (!ids.includes(bookId)) {
    ids = [...state.books]
      .sort((left, right) => left.title.localeCompare(right.title, undefined, { sensitivity: "base" }))
      .map((book) => book.id);
  }
  const index = ids.indexOf(bookId);
  return {
    previous: index > 0 ? ids[index - 1] : null,
    next: index >= 0 && index < ids.length - 1 ? ids[index + 1] : null,
  };
};

const updateBookDetailNavigation = () => {
  const neighbors = bookDetailNeighbors(state.bookDetailId);
  const previousButton = $("#book-detail-previous");
  const nextButton = $("#book-detail-next");
  previousButton.disabled = !neighbors.previous;
  nextButton.disabled = !neighbors.next;
  previousButton.dataset.bookId = neighbors.previous || "";
  nextButton.dataset.bookId = neighbors.next || "";
};

const renderBookDetail = (book, insights) => {
  const cover = safeImageUrl(book.cover_image_url);
  const catalogueUrl = safeImageUrl(book.catalogue_url);
  const publicationLabel = book.publication_date ? formatDate(book.publication_date) : "Not recorded";
  const averageRating = insights.average_rating === null ? "—" : Number(insights.average_rating).toFixed(1);
  const ratingStars = insights.average_rating === null
    ? "No ratings yet"
    : `${"★".repeat(Math.round(insights.average_rating))}${"☆".repeat(5 - Math.round(insights.average_rating))}`;
  const meetings = insights.meetings.length
    ? insights.meetings.map((meeting) => `<button class="book-history-entry" type="button" data-open-book-meeting="${meeting.id}"><span class="book-history-date">${escapeHtml(formatDate(meeting.meeting_date))}</span><div><strong>${meeting.status === "completed" ? "Completed session" : "Planned session"}</strong><p>${meeting.discussion_notes ? escapeHtml(meeting.discussion_notes) : "No discussion recap has been added."}</p><small>${meeting.attendance_count} of ${meeting.roster_count} attended${meeting.pages_read ? ` · ${meeting.pages_read.toLocaleString()} reader-pages` : ""}</small></div><b>→</b></button>`).join("")
    : '<div class="book-detail-empty"><strong>No meetings yet</strong><p>This title is still waiting for its place in the club timeline.</p></div>';
  const reviews = insights.ratings.length
    ? insights.ratings.map((rating) => `<article class="book-review"><header><div class="review-avatar">${escapeHtml(initials(rating.participant_name))}</div><div><strong>${escapeHtml(rating.participant_name)}</strong><span aria-label="${rating.rating} out of 5 stars">${"★".repeat(rating.rating)}${"☆".repeat(5 - rating.rating)}</span></div></header><p>${escapeHtml(rating.review_text || "Rated without a written review.")}</p></article>`).join("")
    : '<div class="book-detail-empty"><strong>No reader reviews yet</strong><p>Ratings submitted by club participants will appear here.</p></div>';
  const genres = (book.genres || "").split(",").map((genre) => genre.trim()).filter(Boolean);

  $("#book-detail-content").innerHTML = `<section class="book-detail-hero"><div class="book-detail-cover">${cover ? `<img src="${escapeHtml(cover)}" alt="Cover of ${escapeHtml(book.title)}" />` : escapeHtml(initials(book.title))}</div><div class="book-detail-intro"><p class="eyebrow"><span></span> Book record</p><h2>${escapeHtml(book.title)}</h2><p class="book-detail-author">by ${escapeHtml(book.author)}</p><div class="book-detail-tags">${genres.map((genre) => `<span>${escapeHtml(genre)}</span>`).join("")}${book.page_count ? `<span>${book.page_count} pages</span>` : ""}</div><p class="book-detail-description">${escapeHtml(book.description || "No synopsis has been added yet.")}</p></div></section>
    <section class="book-detail-metrics" aria-label="Book performance"><article><span>Average rating</span><strong>${averageRating}<small>/5</small></strong><p class="metric-stars">${ratingStars}</p></article><article><span>Club sessions</span><strong>${insights.meetings.length}</strong><p>${insights.meetings.length === 1 ? "meeting" : "meetings"} in the timeline</p></article><article><span>Total attendance</span><strong>${insights.total_attendance}</strong><p>reader visits</p></article><article><span>Reading impact</span><strong>${insights.reading_impact_pages.toLocaleString()}</strong><p>pages × attendees</p></article></section>
    <div class="book-detail-grid"><section class="book-detail-panel"><div class="detail-section-heading"><div><p class="eyebrow"><span></span> Club history</p><h3>Meetings &amp; discussion</h3></div><span>${insights.meetings.length}</span></div><div class="book-history-list">${meetings}</div></section>
    <section class="book-detail-panel"><div class="detail-section-heading"><div><p class="eyebrow"><span></span> Reader response</p><h3>Ratings &amp; reviews</h3></div><span>${insights.rating_count}</span></div><div class="book-review-list">${reviews}</div></section></div>
    <div class="book-detail-grid book-detail-lower"><section class="book-detail-panel"><div class="detail-section-heading"><div><p class="eyebrow"><span></span> Edition details</p><h3>About this book</h3></div></div><dl class="book-facts"><div><dt>Published</dt><dd>${escapeHtml(publicationLabel)}</dd></div><div><dt>Publisher</dt><dd>${escapeHtml(book.publisher || "Not recorded")}</dd></div><div><dt>ISBN</dt><dd>${escapeHtml(book.isbn || "Not recorded")}</dd></div><div><dt>Series</dt><dd>${escapeHtml(book.series || "Not part of a recorded series")}</dd></div></dl>${catalogueUrl ? `<a class="book-catalogue-link" href="${escapeHtml(catalogueUrl)}" target="_blank" rel="noopener">View library catalogue record ↗</a>` : ""}</section>
    <section class="book-detail-panel book-notes-panel"><div class="detail-section-heading"><div><p class="eyebrow"><span></span> Facilitator notes</p><h3>Ideas worth returning to</h3></div></div><p>${escapeHtml(book.discussion_notes || "No book-club notes have been added yet. Use Edit book to capture themes, context, or discussion ideas.")}</p></section></div>`;
};

const openBookDetail = async (bookId) => {
  const book = state.books.find((entry) => entry.id === Number(bookId));
  if (!book) return;
  state.bookDetailId = book.id;
  updateBookDetailNavigation();
  const dialog = $("#book-detail-dialog");
  $("#book-detail-content").innerHTML = '<div class="book-detail-loading"><span></span><p>Opening the book record…</p></div>';
  if (!dialog.open) dialog.showModal();
  try {
    const insights = await request(`/bookclub/books/${book.id}/insights`);
    if (state.bookDetailId === book.id) renderBookDetail(book, insights);
  } catch (error) {
    $("#book-detail-content").innerHTML = `<div class="book-detail-empty large"><strong>Could not open this book</strong><p>${escapeHtml(error.message)}</p></div>`;
  }
};

const renderMeetingView = () => {
  const meeting = currentMeeting();
  $("#edit-meeting").disabled = !meeting;
  const cover = $("#meeting-cover");
  cover.hidden = !meeting;
  if (!meeting) {
    $("#meeting-heading").textContent = "Add your first meeting";
    $("#meeting-intro").textContent =
      "Set the next book and date to begin building the club calendar.";
  } else {
    const coverUrl = safeImageUrl(meeting.book.cover_image_url);
    cover.innerHTML = coverUrl
      ? `<img src="${escapeHtml(coverUrl)}" alt="" />`
      : escapeHtml(initials(meeting.book.title));
    $("#meeting-heading").textContent = meeting.book.title;
    $("#meeting-intro").textContent = [
      `by ${meeting.book.author}`,
      formatDate(meeting.meeting_date),
      meeting.meeting_time,
      meeting.location,
    ]
      .filter(Boolean)
      .join(" · ");
  }
  $("#roster-stat").textContent = state.roster.length;
  $("#new-registrant-stat").textContent = state.roster.filter(
    (entry) => entry.member.is_new_registrant,
  ).length;
  $("#attendance-stat").textContent = state.roster.filter(
    (entry) => entry.attended,
  ).length;
  renderSessionControls();
  renderDiscussionNotes();
  $("#roster-add-search").value = "";
  $("#roster-add-results").hidden = true;
  renderRoster();
  renderGiveaway();
  renderPostMeetingRecap();
  renderReminderPanel();

  const showArchive = Boolean(meeting?.archived_at) && !state.viewingEdit;
  $("#meeting-archive-view").hidden = !showArchive;
  $("#meeting-edit-view").hidden = showArchive;
  if (showArchive) renderArchiveView();
};

const chronologicalMeetings = () => [...state.meetings].sort(
  (a, b) => a.meeting_date.localeCompare(b.meeting_date) || a.id - b.id,
);

const renderSessionControls = () => {
  const meeting = currentMeeting();
  const ordered = chronologicalMeetings();
  const index = ordered.findIndex((entry) => entry.id === meeting?.id);
  const previous = index > 0 ? ordered[index - 1] : null;
  const next = index >= 0 && index < ordered.length - 1 ? ordered[index + 1] : null;
  const previousButton = $("#previous-meeting");
  const nextButton = $("#next-meeting");
  previousButton.disabled = !previous;
  nextButton.disabled = !next;
  previousButton.dataset.meetingId = previous?.id || "";
  nextButton.dataset.meetingId = next?.id || "";
  $("#meeting-position").textContent = meeting
    ? `${index + 1} of ${ordered.length}`
    : "No meetings";
  const effectiveStatus = effectiveMeetingStatus(meeting);
  const toggleCompletedButton = $("#toggle-completed");
  toggleCompletedButton.disabled = !meeting;
  toggleCompletedButton.textContent = MEETING_STATUS_LABELS[effectiveStatus];
  toggleCompletedButton.className = `status-pill meeting-status-badge ${effectiveStatus}`;
  toggleCompletedButton.title =
    meeting?.status === "completed" ? "Reopen this session" : "Mark this session completed";
  $("#day-of-mode").disabled = !meeting;
  $("#day-of-mode").innerHTML = state.dayOfMode
    ? '<span aria-hidden="true"><svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M8 3v3a2 2 0 0 1-2 2H3" /><path d="M21 8h-3a2 2 0 0 1-2-2V3" /><path d="M3 16h3a2 2 0 0 1 2 2v3" /><path d="M16 21v-3a2 2 0 0 1 2-2h3" /></svg></span> Exit session view'
    : '<span aria-hidden="true"><svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M8 3H5a2 2 0 0 0-2 2v3" /><path d="M21 8V5a2 2 0 0 0-2-2h-3" /><path d="M3 16v3a2 2 0 0 0 2 2h3" /><path d="M16 21h3a2 2 0 0 0 2-2v-3" /></svg></span> Run session';
};

const renderDiscussionNotes = () => {
  const meeting = currentMeeting();
  const textarea = $("#discussion-notes");
  textarea.disabled = !meeting;
  $("#save-discussion-notes").disabled = !meeting;
  if (!state.discussionNotesDirty) {
    textarea.value = meeting?.discussion_notes || "";
  }
  $("#discussion-notes-status").textContent = state.discussionNotesDirty
    ? "Unsaved changes"
    : meeting?.discussion_notes
      ? "Notes saved"
      : "No notes yet";
};

const sessionRecap = () => {
  const meeting = currentMeeting();
  if (!meeting) return null;
  const attended = state.roster.filter((entry) => entry.attended);
  const notAttended = state.roster.filter((entry) => !entry.attended);
  const newMembers = state.roster.filter((entry) => isFirstAttendedSession(entry));
  const pages = attended.length * (meeting.book.page_count || 0);
  const winner = meeting.giveaway_winner_member_id
    ? state.members.find(
        (member) => member.id === meeting.giveaway_winner_member_id,
      )
    : null;
  const followups = state.roster.reduce(
    (count, entry) => count + memberPendingBadges(entry.member).length,
    0,
  );
  return { meeting, attended, notAttended, newMembers, pages, winner, followups };
};

const sessionRecapText = () => {
  const recap = sessionRecap();
  if (!recap) return "";
  const { meeting, attended, pages, winner, followups } = recap;
  const participantNotes = state.roster
    .filter((entry) => entry.notes)
    .map((entry) => `- ${entry.member.name}: ${entry.notes}`);
  return [
    `${meeting.book.title} — ${formatDate(meeting.meeting_date)}`,
    `Status: ${meetingStatusLabel(meeting)}`,
    `Attendance: ${attended.length} of ${state.roster.length}`,
    meeting.book.page_count
      ? `Pages read together: ${pages.toLocaleString("en-CA")}`
      : null,
    `Giveaway winner: ${winner?.name || "Not drawn"}`,
    `Follow-ups remaining: ${followups}`,
    meeting.discussion_notes
      ? `Discussion notes:\n${meeting.discussion_notes}`
      : null,
    participantNotes.length
      ? `Participant notes:\n${participantNotes.join("\n")}`
      : null,
  ].filter(Boolean).join("\n\n");
};

// The archive view is a read-only presentation of the same live data the
// edit view uses — archiving only changes which view opens by default, it
// never freezes a snapshot. Editing (roster, notes, giveaway) only happens
// in the edit view, reached via "Edit session".
const renderArchiveView = () => {
  const recap = sessionRecap();
  if (!recap) return;
  const { meeting, attended, notAttended, newMembers, pages, winner, followups } = recap;
  const cover = $("#archive-cover");
  const coverUrl = safeImageUrl(meeting.book.cover_image_url);
  cover.innerHTML = coverUrl
    ? `<img src="${escapeHtml(coverUrl)}" alt="" />`
    : escapeHtml(initials(meeting.book.title));
  $("#archive-heading").textContent = meeting.book.title;
  $("#archive-intro").textContent = [
    `by ${meeting.book.author}`,
    formatDate(meeting.meeting_date),
    meeting.meeting_time,
    meeting.location,
  ]
    .filter(Boolean)
    .join(" · ");

  const nameList = (entries, emptyMessage) =>
    entries.length
      ? `<ul class="archive-name-list">${entries
          .map((entry) => `<li>${escapeHtml(entry.member.name)}</li>`)
          .join("")}</ul>`
      : `<p class="archive-empty">${escapeHtml(emptyMessage)}</p>`;

  $("#archive-content").innerHTML = `
    <div class="archive-stats-row">
      <article class="archive-stat"><span class="stat-icon green">◎</span><div><strong>${attended.length}<small> / ${state.roster.length}</small></strong><span>Attended</span></div></article>
      <article class="archive-stat"><span class="stat-icon gold">✦</span><div><strong>${newMembers.length}</strong><span>First-timers</span></div></article>
      <article class="archive-stat"><span class="stat-icon orange">▥</span><div><strong>${pages.toLocaleString("en-CA")}</strong><span>Pages read together</span></div></article>
      <article class="archive-stat"><span class="stat-icon blue">✉</span><div><strong>${followups}</strong><span>Follow-ups remaining</span></div></article>
    </div>

    <section class="panel archive-giveaway-panel">
      <div class="giveaway-orbit" aria-hidden="true"><span>★</span></div>
      ${
        winner
          ? `<p class="winner-name">${escapeHtml(winner.name)}</p><p>Monthly book giveaway winner</p>`
          : `<p>No giveaway winner was drawn for this session.</p>`
      }
    </section>

    <section class="archive-attendance-lists">
      <div>
        <h3>Attended (${attended.length})</h3>
        ${nameList(attended, "No one was marked as attended.")}
      </div>
      <div>
        <h3>Didn't make it (${notAttended.length})</h3>
        ${nameList(notAttended, "Everyone on the roster attended.")}
      </div>
      ${
        newMembers.length
          ? `<div>
              <h3>First meeting (${newMembers.length})</h3>
              ${nameList(newMembers, "")}
            </div>`
          : ""
      }
    </section>

    ${
      meeting.discussion_notes
        ? `<section class="panel archive-notes-panel">
            <div class="panel-heading compact"><div><p class="eyebrow"><span></span> The conversation</p><h2>Discussion notes</h2></div></div>
            <p class="archive-notes-text">${escapeHtml(meeting.discussion_notes)}</p>
          </section>`
        : ""
    }

    ${
      state.roster.some((entry) => entry.notes)
        ? `<section class="panel archive-notes-panel">
            <div class="panel-heading compact"><div><p class="eyebrow"><span></span> Individually</p><h2>Participant notes</h2></div></div>
            <ul class="archive-participant-notes">${state.roster
              .filter((entry) => entry.notes)
              .map(
                (entry) =>
                  `<li><strong>${escapeHtml(entry.member.name)}</strong><span>${escapeHtml(entry.notes)}</span></li>`,
              )
              .join("")}</ul>
          </section>`
        : ""
    }
  `;
};

const setSessionRecapExpanded = (expanded) => {
  const body = $("#session-recap-body");
  const toggle = $("#toggle-session-recap");
  body.hidden = !expanded;
  toggle.setAttribute("aria-expanded", String(expanded));
  $("#recap-toggle-label").textContent = expanded ? "Hide recap" : "Show recap";
  $("#post-meeting-recap").classList.toggle("is-collapsed", !expanded);
};

const renderPostMeetingRecap = () => {
  const recap = sessionRecap();
  const grid = $("#recap-grid");
  const panel = $("#post-meeting-recap");
  $("#copy-session-recap").disabled = !recap;
  $("#toggle-session-recap").disabled = !recap;
  if (!recap) {
    grid.innerHTML = '<div class="empty-card"><p>Add a meeting to create its recap.</p></div>';
    $("#recap-narrative").textContent = "";
    panel.dataset.meetingId = "";
    panel.dataset.relevant = "false";
    panel.dataset.completed = "false";
    setSessionRecapExpanded(false);
    return;
  }
  const { meeting, attended, pages, winner, followups } = recap;
  const relevant = meeting.status === "completed" || attended.length > 0 || Boolean(meeting.discussion_notes);
  const meetingChanged = panel.dataset.meetingId !== String(meeting.id);
  const becameRelevant = relevant && panel.dataset.relevant !== "true";
  const becameComplete = meeting.status === "completed" && panel.dataset.completed !== "true";
  if (meetingChanged || becameRelevant || becameComplete) setSessionRecapExpanded(relevant);
  panel.dataset.meetingId = String(meeting.id);
  panel.dataset.relevant = String(relevant);
  panel.dataset.completed = String(meeting.status === "completed");
  $("#recap-context").textContent = meeting.status === "completed"
    ? "This session is complete. The recap is ready to share or file."
    : relevant
      ? "This live summary updates as attendance and session details change."
      : "The recap will open when attendance or discussion notes are added.";
  grid.innerHTML = `
    <article><span>◎</span><strong>${attended.length}<small> / ${state.roster.length}</small></strong><p>Attended</p></article>
    <article><span>∑</span><strong>${meeting.book.page_count ? pages.toLocaleString("en-CA") : "—"}</strong><p>Pages read together</p></article>
    <article><span>★</span><strong>${escapeHtml(winner?.name || "Not drawn")}</strong><p>Giveaway winner</p></article>
    <article><span>↻</span><strong>${followups}</strong><p>Follow-ups remaining</p></article>`;
  $("#recap-narrative").textContent = attended.length
    ? `${attended.length} ${attended.length === 1 ? "reader was" : "readers were"} part of the conversation about ${meeting.book.title}.`
    : "Attendance has not been recorded for this session yet.";
  panel.classList.toggle(
    "is-complete",
    meeting.status === "completed",
  );
};

// A member's first-ever attended meeting is this one: their lifetime
// attended_count is 1 and that single attendance falls on this meeting's
// date. Guarded by entry.attended so the badge never shows before the
// roster checkbox is actually ticked.
const isFirstAttendedSession = (entry) => {
  const meeting = currentMeeting();
  if (!meeting || !entry.attended) return false;
  const summary = state.participation.find((row) => row.member.id === entry.member.id);
  return summary?.attended_count === 1 && summary.last_attended_date === meeting.meeting_date;
};

const renderRoster = () => {
  const body = $("#roster-table");
  if (!state.meetingId) {
    body.innerHTML = '<div class="roster-empty-state"><p>Add a meeting to start building its roster.</p></div>';
    return;
  }
  const entries = state.roster;
  if (!entries.length) {
    const meeting = currentMeeting();
    const upcoming = Boolean(meeting) && meeting.meeting_date >= today();
    const ordered = chronologicalMeetings();
    const hasPrevious = ordered.findIndex((entry) => entry.id === meeting?.id) > 0;
    const importPrompt = upcoming && hasPrevious
      ? ', or <button class="text-button" type="button" id="import-previous-roster">import attendees from the previous session</button>'
      : "";
    body.innerHTML = `<div class="roster-empty-state"><p>No one has been added yet — search above to build this meeting roster${importPrompt}.</p></div>`;
    if (upcoming && hasPrevious) {
      $("#import-previous-roster").addEventListener("click", importPreviousRoster);
    }
    return;
  }
  body.innerHTML = entries
    .map((entry) => {
      const member = entry.member;
      const attended = entry.attended;
      const newMemberBadgeHtml = isFirstAttendedSession(entry)
        ? '<span class="status-pill first-session-badge" title="First session attended">✦ First meeting</span>'
        : "";
      const pendingBadgeHtml = memberPendingBadges(member)
        .map(
          (badge) => `<button class="status-pill ${badge.className} roster-email-badge" type="button" data-open-followup="${member.id}" data-stage="${badge.stage}">${escapeHtml(badge.label)}</button>`,
        )
        .join("");
      const noteIndicatorHtml = entry.notes
        ? `<span class="roster-note-indicator" title="${escapeHtml(entry.notes)}">✎ Note</span>`
        : "";
      return `<article class="roster-member-card ${attended ? "is-attended" : ""}" data-roster-toggle="${member.id}" role="button" tabindex="0" aria-pressed="${attended ? "true" : "false"}" aria-label="${escapeHtml(member.name)}, ${attended ? "attended. Tap to mark as not attended." : "tap to mark as attended."}">
        <div class="roster-card-main">
          <span class="avatar">${escapeHtml(initials(member.name))}</span>
          <div class="roster-card-identity">
            <strong>${escapeHtml(member.name)}</strong>
            <span class="roster-card-status">${attended ? "Attended" : "Tap to check in"}</span>
          </div>
        </div>
        <div class="roster-card-flags">${newMemberBadgeHtml}${pendingBadgeHtml}${noteIndicatorHtml}</div>
        <details class="roster-card-menu" data-roster-menu>
          <summary class="roster-card-menu-trigger" aria-label="More actions for ${escapeHtml(member.name)}">⋮</summary>
          <div class="roster-card-menu-panel">
            <button type="button" data-participant-note="${member.id}"><svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21.174 6.812a1 1 0 0 0-3.986-3.987L3.842 16.174a2 2 0 0 0-.5.83l-1.321 4.352a.5.5 0 0 0 .623.622l4.353-1.32a2 2 0 0 0 .83-.497z" /><path d="m15 5 4 4" /></svg> ${entry.notes ? "Edit note" : "Add note"}</button>
            <button type="button" data-send-book="${member.id}"><svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M14.536 21.686a.5.5 0 0 0 .937-.024l6.5-19a.496.496 0 0 0-.635-.635l-19 6.5a.5.5 0 0 0-.024.937l7.93 3.18a2 2 0 0 1 1.112 1.11z" /><path d="m21.854 2.147-10.94 10.939" /></svg> Send a book</button>
            <button type="button" class="roster-menu-danger" data-remove-from-roster="${member.id}"><svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" /><circle cx="9" cy="7" r="4" /><line x1="17" x2="22" y1="8" y2="13" /><line x1="22" x2="17" y1="8" y2="13" /></svg> Remove member</button>
          </div>
        </details>
      </article>`;
    })
    .join("");
};

const saveParticipation = async (memberId, changes) => {
  const saved = await request(
    `/bookclub/meetings/${state.meetingId}/members/${memberId}`,
    { method: "PUT", body: JSON.stringify(changes) },
  );
  const index = state.roster.findIndex((entry) => entry.member_id === memberId);
  if (index >= 0) state.roster[index] = saved;
  else state.roster.push(saved);
  if ("attended" in changes) {
    state.participation = await request("/bookclub/members/participation-summary");
  }
  renderMeetingView();
};

const importPreviousRoster = async () => {
  const meeting = currentMeeting();
  if (!meeting) return;
  try {
    state.roster = await request(
      `/bookclub/meetings/${meeting.id}/roster/import-previous`,
      { method: "POST" },
    );
    renderMeetingView();
    showToast("Imported attendees from the previous session.");
  } catch (error) {
    showToast(error.message);
  }
};

const renderGiveaway = () => {
  const meeting = currentMeeting();
  const content = $("#giveaway-content");
  const winner = meeting?.giveaway_winner_member_id
    ? state.members.find(
        (member) => member.id === meeting.giveaway_winner_member_id,
      )
    : null;
  if (winner) {
    content.innerHTML = `<div class="giveaway-orbit"><span>★</span></div><p class="winner-name">${escapeHtml(winner.name)}</p><p>Monthly book giveaway winner</p><button class="secondary-button" id="draw-winner" type="button"><svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M11.017 2.814a1 1 0 0 1 1.966 0l1.051 5.558a2 2 0 0 0 1.594 1.594l5.558 1.051a1 1 0 0 1 0 1.966l-5.558 1.051a2 2 0 0 0-1.594 1.594l-1.051 5.558a1 1 0 0 1-1.966 0l-1.051-5.558a2 2 0 0 0-1.594-1.594l-5.558-1.051a1 1 0 0 1 0-1.966l5.558-1.051a2 2 0 0 0 1.594-1.594z" /><path d="M20 2v4" /><path d="M22 4h-4" /><circle cx="4" cy="20" r="2" /></svg> Draw again</button>`;
  } else {
    content.innerHTML = '<div class="giveaway-orbit"><span>★</span></div><p>Draw one name at random from everyone marked as attended.</p><button class="primary-button" id="draw-winner" type="button"><svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M11.017 2.814a1 1 0 0 1 1.966 0l1.051 5.558a2 2 0 0 0 1.594 1.594l5.558 1.051a1 1 0 0 1 0 1.966l-5.558 1.051a2 2 0 0 0-1.594 1.594l-1.051 5.558a1 1 0 0 1-1.966 0l-1.051-5.558a2 2 0 0 0-1.594-1.594l-5.558-1.051a1 1 0 0 1 0-1.966l5.558-1.051a2 2 0 0 0 1.594-1.594z" /><path d="M20 2v4" /><path d="M22 4h-4" /><circle cx="4" cy="20" r="2" /></svg> Draw a name</button>';
  }
  $("#draw-winner").addEventListener("click", drawWinner);
  $("#giveaway-inline-status").textContent = winner ? `${winner.name} won` : "No winner yet";
};

const openGiveawayDialog = () => {
  if (!currentMeeting()) return showToast("Add a meeting first.");
  renderGiveaway();
  $("#giveaway-dialog").showModal();
};

const drawWinner = async () => {
  const meeting = currentMeeting();
  if (!meeting) return showToast("Add a meeting first.");
  const redraw = Boolean(meeting.giveaway_winner_member_id);
  if (redraw && !window.confirm("Replace the saved giveaway winner?")) return;
  $("#giveaway-content").innerHTML = '<div class="giveaway-orbit drawing" aria-hidden="true"><span>★</span></div><p>Drawing a name…</p>';
  try {
    const [result] = await Promise.all([
      request(
        `/bookclub/meetings/${meeting.id}/giveaway/draw${redraw ? "?redraw=true" : ""}`,
        { method: "POST" },
      ),
      new Promise((resolve) => setTimeout(resolve, 5000)),
    ]);
    meeting.giveaway_winner_member_id = result.member.id;
    renderGiveaway();
    renderPostMeetingRecap();
    showToast(`${result.member.name} wins this month’s book!`);
  } catch (error) {
    renderGiveaway();
    showToast(error.message);
  }
};

const DELIVERY_LABELS = { none: "No copy", pickup: "Pickup at PBRL", transfer: "Send to branch" };

const needsArrivalConfirmation = (member) => {
  if (!member.transit_label_printed_at) return false;
  if (!member.arrival_email_sent_at) return true;
  return new Date(member.transit_label_printed_at) > new Date(member.arrival_email_sent_at);
};

// New registrants can need a welcome, while any member can need an arrival
// follow-up after a transit label is printed. Both are tracked on the member
// and use the selected meeting for book/date template details.
const memberFollowupStages = (member) => {
  const stages = [];
  if (member.is_new_registrant && !member.onboarding_email_sent_at) stages.push("welcome");
  if (needsArrivalConfirmation(member)) stages.push("arrival");
  return stages;
};

const STAGE_LABELS = {
  welcome: "Welcome email needed",
  arrival: "Awaiting book arrival",
};

const renderReminderPanel = () => {
  const meeting = currentMeeting();
  const status = $("#reminder-status");
  const countEl = $("#reminder-recipient-count");
  if (!meeting) {
    status.textContent = "Add a meeting first.";
    countEl.textContent = "";
    $("#reminder-inline-status").textContent = "Add a meeting first";
    $("#reminder-trigger-label").textContent = "Send Reminder";
    $("#open-reminder-dialog").classList.remove("is-sent");
    $("#open-reminder-dialog").disabled = true;
    return;
  }
  $("#open-reminder-dialog").disabled = false;
  $("#open-reminder-dialog").classList.toggle("is-sent", Boolean(meeting.reminder_sent_at));
  $("#reminder-trigger-label").textContent = meeting.reminder_sent_at
    ? "Reminder Sent"
    : "Send Reminder";
  status.textContent = meeting.reminder_sent_at
    ? `Reminder sent on ${formatDate(meeting.reminder_sent_at.slice(0, 10))}.`
    : "Not sent yet.";
  $("#reminder-inline-status").textContent = meeting.reminder_sent_at
    ? `Sent ${formatDate(meeting.reminder_sent_at.slice(0, 10))}`
    : "Not sent yet";
  countEl.textContent = state.roster.length
    ? `${state.roster.length} ${state.roster.length === 1 ? "person" : "people"} on this meeting's roster.`
    : "No one has been added to this meeting yet.";
};

const refreshCurrentMeeting = async () => {
  const updated = await request(`/bookclub/meetings/${state.meetingId}`);
  const index = state.meetings.findIndex((entry) => entry.id === updated.id);
  if (index >= 0) state.meetings[index] = updated;
  return updated;
};

const refreshMember = async (memberId) => {
  const updated = await request(`/bookclub/members/${memberId}`);
  const index = state.members.findIndex((entry) => entry.id === updated.id);
  if (index >= 0) state.members[index] = updated;
  const rosterEntry = state.roster.find((entry) => entry.member_id === updated.id);
  if (rosterEntry) rosterEntry.member = updated;
  return updated;
};

const memberPendingBadges = (member) => memberFollowupStages(member).map((stage) => ({
  stage,
  label: stage === "arrival" && member.destination_branch
    ? `${STAGE_LABELS[stage]} — ${member.destination_branch}`
    : STAGE_LABELS[stage],
  className: stage === "arrival" ? "arrival-badge" : "new-badge",
}));

const renderMembers = () => {
  const query = state.memberQuery.trim().toLowerCase();
  const participationByMember = new Map(
    state.participation.map((row) => [row.member.id, row]),
  );
  const members = state.members
    .filter((member) =>
      [member.name, member.email].join(" ").toLowerCase().includes(query),
    )
    .sort((memberA, memberB) => {
      const rowA = participationByMember.get(memberA.id);
      const rowB = participationByMember.get(memberB.id);
      if (state.memberSort === "attendance") {
        const rateA = rowA?.meetings_total ? rowA.attended_count / rowA.meetings_total : -1;
        const rateB = rowB?.meetings_total ? rowB.attended_count / rowB.meetings_total : -1;
        return rateB - rateA || memberA.name.localeCompare(memberB.name);
      }
      if (state.memberSort === "last_attended") {
        return (rowB?.last_attended_date || "").localeCompare(rowA?.last_attended_date || "") || memberA.name.localeCompare(memberB.name);
      }
      if (state.memberSort === "pages") {
        return (rowB?.pages_read || 0) - (rowA?.pages_read || 0) || memberA.name.localeCompare(memberB.name);
      }
      if (state.memberSort === "joined") {
        return memberB.joined_on.localeCompare(memberA.joined_on) || memberA.name.localeCompare(memberB.name);
      }
      return memberA.name.localeCompare(memberB.name);
    });
  const activeCount = state.members.filter((member) => member.active).length;
  const totalMeetings = state.participation.reduce((total, row) => total + row.meetings_total, 0);
  const totalAttended = state.participation.reduce((total, row) => total + row.attended_count, 0);
  const totalPages = state.participation.reduce((total, row) => total + row.pages_read, 0);
  const lapsedCount = state.participation.filter(
    (row) => row.member.active && row.meetings_since_last_attended >= 3,
  ).length;
  $("#member-stat-active").textContent = activeCount;
  $("#member-stat-attendance").textContent = totalMeetings
    ? `${Math.round((totalAttended / totalMeetings) * 100)}%`
    : "—";
  $("#member-stat-pages").textContent = totalPages.toLocaleString("en-CA");
  $("#member-stat-lapsed").textContent = lapsedCount;
  $("#member-count").textContent = query
    ? `${members.length} matching · ${state.members.length} total`
    : `${activeCount} active · ${state.members.length} total`;
  $("#members-grid").innerHTML = members.length
    ? members
        .map((member) => {
          const participation = participationByMember.get(member.id);
          const meetingsTotal = participation?.meetings_total || 0;
          const attendedCount = participation?.attended_count || 0;
          const attendanceRate = meetingsTotal
            ? Math.round((attendedCount / meetingsTotal) * 100)
            : 0;
          const lapsed = member.active && (participation?.meetings_since_last_attended || 0) >= 3;
          const badgeHtml = memberPendingBadges(member)
            .map(
              (badge) => `<button class="status-pill ${badge.className} jump-badge" type="button" data-jump-to-pending="${member.id}" data-stage="${badge.stage}">${escapeHtml(badge.label)}</button>`,
            )
            .join("");
          return `<article class="member-profile-card ${lapsed ? "needs-attention" : ""}">
            <header class="member-profile-heading">
              <div class="member-cell"><span class="avatar">${escapeHtml(initials(member.name))}</span><div><strong>${escapeHtml(member.name)}</strong><span class="member-email-row"><small class="member-email">${escapeHtml(member.email)}</small><button class="copy-email-button" type="button" data-copy-email="${escapeHtml(member.email)}" aria-label="Copy ${escapeHtml(member.name)}'s email address" title="Copy email address"><svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect width="14" height="14" x="8" y="8" rx="2" ry="2" /><path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2" /></svg></button></span></div></div>
              <span class="status-pill ${member.active ? "" : "inactive"}">${member.active ? "Active" : "Inactive"}</span>
            </header>
            <div class="member-badge-row">${member.participant_account_linked ? '<span class="status-pill">Portal account</span>' : ""}${lapsed ? '<span class="status-pill attention-badge">May need a hello</span>' : ""}${badgeHtml}</div>
            <div class="member-engagement">
              <div class="attendance-summary"><span>Attendance</span><strong>${attendedCount}<small> / ${meetingsTotal}</small></strong><div class="attendance-track" role="img" aria-label="${attendanceRate}% attendance"><span style="width: ${attendanceRate}%"></span></div></div>
              <div class="giveaway-summary pages-summary"><span>Pages read</span><strong>${(participation?.pages_read || 0).toLocaleString("en-CA")}<small> pages</small></strong></div>
            </div>
            <dl class="member-detail-list">
              <div><dt>Joined</dt><dd>${escapeHtml(formatDate(member.joined_on))}</dd></div>
              <div><dt>Last attended</dt><dd>${participation?.last_attended_date ? escapeHtml(formatDate(participation.last_attended_date)) : "Not yet"}</dd></div>
              <div><dt>Last contacted</dt><dd>${participation?.last_contacted_at ? escapeHtml(formatDate(participation.last_contacted_at.slice(0, 10))) : "Not yet"}</dd></div>
            </dl>
            ${member.notes ? `<p class="member-card-notes">${escapeHtml(member.notes)}</p>` : ""}
            <footer class="member-profile-actions"><button class="quiet-button" type="button" data-member-history="${member.id}"><svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8" /><path d="M3 3v5h5" /><path d="M12 7v5l4 2" /></svg> View history</button><button class="secondary-button" type="button" data-edit-member="${member.id}"><svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21.174 6.812a1 1 0 0 0-3.986-3.987L3.842 16.174a2 2 0 0 0-.5.83l-1.321 4.352a.5.5 0 0 0 .623.622l4.353-1.32a2 2 0 0 0 .83-.497z" /><path d="m15 5 4 4" /></svg> Edit member</button></footer>
          </article>`;
        })
        .join("")
    : `<div class="empty-card member-directory-empty"><span>◎</span><h3>${query ? "No matching members" : "No members yet"}</h3><p>${query ? "Try a different name or email." : "Add the first person to begin building your club community."}</p></div>`;
};

const openFollowupDialog = (memberId, stage) => {
  const member = state.members.find((entry) => entry.id === memberId);
  if (!member) return showToast("Member not found.");
  const dialog = $("#followup-dialog");
  dialog.dataset.memberId = memberId;
  dialog.dataset.stage = stage;
  $("#followup-title").textContent = stage === "arrival"
    ? "Book arrival follow-up"
    : "Welcome email";
  $("#followup-member").innerHTML = `<span class="avatar">${escapeHtml(initials(member.name))}</span><div><strong>${escapeHtml(member.name)}</strong><small>${escapeHtml(member.email)}</small></div>`;
  $("#followup-context").textContent = stage === "arrival"
    ? `${member.name}'s book was sent to ${member.destination_branch || "their branch"}. Use this when it arrives to confirm pickup details.`
    : `Welcome ${member.name} and share the book and meeting details for this session.`;
  const copyAddressButton = $("#followup-copy-address");
  const copyButton = $("#followup-copy");
  const markSentButton = $("#followup-mark-sent");
  const sendButton = $("#followup-send");
  copyAddressButton.dataset.copyEmail = member.email;
  copyButton.dataset.copyRegistrantEmail = memberId;
  copyButton.dataset.stage = stage;
  markSentButton.dataset.markRegistrantSent = memberId;
  markSentButton.dataset.stage = stage;
  sendButton.dataset.sendRegistrantEmail = memberId;
  sendButton.dataset.stage = stage;
  dialog.showModal();
};

const jumpToPendingMeeting = async (memberId, stage) => {
  try {
    if (state.roster.some((entry) => entry.member_id === memberId)) {
      await setView("meeting");
      return openFollowupDialog(memberId, stage);
    }
    const history = await request(`/bookclub/members/${memberId}/history`);
    const targetMeeting = history[0]?.meeting;
    if (!targetMeeting) return showToast("No meeting found for this member.");
    state.meetingId = targetMeeting.id;
    await loadSelectedMeeting();
    await setView("meeting");
    openFollowupDialog(memberId, stage);
  } catch (error) {
    showToast(error.message);
  }
};

let memberDialogAddToRoster = false;

const openMemberDialog = (member = null, { addToRoster = false, prefillName = "" } = {}) => {
  memberDialogAddToRoster = addToRoster && !member;
  const form = $("#member-form");
  form.reset();
  form.elements.id.value = member?.id || "";
  form.elements.name.value = member?.name || prefillName;
  form.elements.email.value = member?.email || "";
  form.elements.joined_on.value = member?.joined_on || today();
  form.elements.active.value = String(member?.active ?? true);
  form.elements.is_new_registrant.value = String(member?.is_new_registrant ?? true);
  form.elements.delivery_method.value = member?.delivery_method || "none";
  form.elements.destination_branch.value = member?.destination_branch || "";
  form.elements.notes.value = member?.notes || "";
  updateMemberDeliveryFieldVisibility();
  $("#member-dialog-title").textContent = member ? "Edit member" : "Add member";
  $("#delete-member").hidden = !member;
  $("#member-error").textContent = "";
  $("#member-dialog").showModal();
};

const updateMemberDeliveryFieldVisibility = () => {
  const form = $("#member-form");
  const isNewRegistrant = form.elements.is_new_registrant.value === "true";
  $("#member-delivery-field").hidden = !isNewRegistrant;
  $("#member-branch-field").hidden =
    !isNewRegistrant || form.elements.delivery_method.value !== "transfer";
};

const openMeetingDialog = (meeting = null) => {
  const form = $("#meeting-form");
  form.reset();
  const selectedBook = meeting
    ? state.books.find((book) => book.id === meeting.book_id)
    : null;
  form.elements.book_id.value = meeting?.book_id || "";
  $("#meeting-book-search").value = selectedBook
    ? `${selectedBook.title} — ${selectedBook.author}`
    : "";
  $("#meeting-book-results").hidden = true;
  $("#meeting-book-results").innerHTML = "";
  form.elements.id.value = meeting?.id || "";
  form.elements.meeting_date.value = meeting?.meeting_date || today();
  form.elements.meeting_time.value = meeting?.meeting_time || "";
  form.elements.meeting_duration_minutes.value = meeting?.meeting_duration_minutes || 90;
  form.elements.location.value = meeting?.location || "PBRL";
  form.elements.notes.value = meeting?.notes || "";
  $("#meeting-dialog-title").textContent = meeting ? "Edit meeting" : "Add meeting";
  $("#delete-meeting").hidden = !meeting;
  $("#meeting-error").textContent = "";
  $("#meeting-dialog").showModal();
};

const openBookDialog = (book = null) => {
  const form = $("#book-form");
  form.reset();
  const fields = [
    "title",
    "author",
    "cover_image_url",
    "description",
    "publication_date",
    "isbn",
    "publisher",
    "page_count",
    "genres",
    "series",
    "catalogue_url",
    "discussion_notes",
  ];
  form.elements.id.value = book?.id || "";
  fields.forEach((field) => {
    form.elements[field].value = book?.[field] || "";
  });
  form.elements.is_past_selection.value = String(book?.is_past_selection ?? false);
  $("#book-dialog-title").textContent = book ? "Edit book" : "Add book";
  $("#book-error").textContent = "";
  const importStatus = $("#import-book-status");
  importStatus.textContent = "Paste a book record link to fill the form automatically.";
  importStatus.className = "field-help";
  $("#import-book").disabled = false;
  $("#book-dialog").showModal();
};

const importBookDetails = async () => {
  const form = $("#book-form");
  const button = $("#import-book");
  const status = $("#import-book-status");
  const catalogueUrl = form.elements.catalogue_url.value.trim();
  if (!catalogueUrl) {
    status.textContent = "Paste a Vaughan Public Libraries book link first.";
    status.className = "field-help error";
    form.elements.catalogue_url.focus();
    return;
  }
  button.disabled = true;
  button.textContent = "Finding details…";
  status.textContent = "Reading the catalogue record…";
  status.className = "field-help";
  try {
    const book = await request("/bookclub/books/import", {
      method: "POST",
      body: JSON.stringify({ catalogue_url: catalogueUrl }),
    });
    [
      "title",
      "author",
      "cover_image_url",
      "description",
      "publication_date",
      "isbn",
      "publisher",
      "page_count",
      "genres",
      "series",
      "catalogue_url",
    ].forEach((field) => {
      form.elements[field].value = book[field] ?? "";
    });
    status.textContent = "Details added. Review them, then save the book.";
    status.className = "field-help success";
  } catch (error) {
    status.textContent = error.message;
    status.className = "field-help error";
  } finally {
    button.disabled = false;
    button.textContent = "Fill book details";
  }
};

const showMemberHistory = async (memberId) => {
  const member = state.members.find((entry) => entry.id === memberId);
  const history = await request(`/bookclub/members/${memberId}/history`);
  const attended = history.filter((entry) => entry.attended);
  const totalPages = attended.reduce(
    (total, entry) => total + (entry.meeting.book.page_count || 0),
    0,
  );
  const giveawaysWon = attended.filter(
    (entry) => entry.meeting.giveaway_winner_member_id === memberId,
  ).length;
  $("#history-title").textContent = `${member.name}’s reading history`;
  const deliveryHtml = member.delivery_method !== "none"
    ? `<p class="history-notes">${escapeHtml(DELIVERY_LABELS[member.delivery_method] || member.delivery_method)}${member.delivery_method === "transfer" && member.destination_branch ? ` — ${escapeHtml(member.destination_branch)}` : ""}</p>`
    : "";
  const notesHtml = member.notes
    ? `<p class="history-notes">${escapeHtml(member.notes)}</p>`
    : "";
  const summaryHtml = `<section class="history-summary-grid" aria-label="Reading totals">
    <article><span>▥</span><strong>${attended.length}</strong><small>Books read</small></article>
    <article><span>∑</span><strong>${totalPages.toLocaleString("en-CA")}</strong><small>Pages read</small></article>
    <article><span>★</span><strong>${giveawaysWon}</strong><small>Giveaways won</small></article>
  </section>`;
  const booksHtml = attended.length
    ? `<div class="history-book-grid">${attended
        .map((entry) => {
          const book = entry.meeting.book;
          const cover = safeImageUrl(book.cover_image_url);
          const won = entry.meeting.giveaway_winner_member_id === memberId;
          return `<article class="history-book-card">
            <div class="history-book-cover">${cover ? `<img src="${escapeHtml(cover)}" alt="" />` : escapeHtml(initials(book.title))}</div>
            <div><span class="history-book-date">${escapeHtml(formatDate(entry.meeting.meeting_date))}</span><strong>${escapeHtml(book.title)}</strong><small>by ${escapeHtml(book.author)}</small><p>${book.page_count ? `${book.page_count.toLocaleString("en-CA")} pages` : "Page count unavailable"}${won ? ' <b>★ Giveaway winner</b>' : ""}</p></div>
          </article>`;
        })
        .join("")}</div>`
    : '<div class="empty-card history-empty"><span>▥</span><h3>No books read yet</h3><p>Books will appear here when this member is marked as attended.</p></div>';
  $("#history-content").innerHTML = summaryHtml + deliveryHtml + notesHtml + booksHtml;
  $("#history-dialog").showModal();
};

const printTransitLabel = async (memberId, destinationBranch) => {
  try {
    const rendered = await request("/bookclub/transit-labels/print", {
      method: "POST",
      body: JSON.stringify({ member_id: memberId, destination_branch: destinationBranch }),
    });
    await refreshMember(memberId);
    renderRoster();
    renderMembers();
    renderPostMeetingRecap();
    renderBranchSuggestions();
    $("#print-sheet").innerHTML = `<article class="print-label">${escapeHtml(rendered.body)}</article>`;
    window.print();
    return true;
  } catch (error) {
    showToast(error.message);
    return false;
  }
};

const loadTemplates = async () => {
  state.templates = await request("/bookclub/templates");
  if (!state.templates.some((item) => item.key === state.templateKey)) {
    state.templateKey = state.templates[0]?.key || null;
  }
  renderTemplates();
};

const renderTemplates = () => {
  $("#template-list").innerHTML = state.templates
    .map(
      (template) => `<button class="template-option ${template.key === state.templateKey ? "active" : ""}" type="button" data-template-key="${template.key}"><strong>${escapeHtml(template.name)}</strong><small>${template.kind === "email" ? "Email" : "Printable label"}</small></button>`,
    )
    .join("");
  const template = state.templates.find((item) => item.key === state.templateKey);
  const form = $("#template-form");
  if (!template) return;
  $("#template-editor-title").textContent = template.name;
  form.elements.name.value = template.name;
  form.elements.subject.value = template.subject || "";
  form.elements.body.value = template.body;
  $("#template-subject-field").hidden = template.kind !== "email";
};

const loadParticipation = async () => {
  state.participation = await request("/bookclub/members/participation-summary");
  renderMembers();
};

const setView = async (view) => {
  state.view = view;
  if (view !== "meeting" && state.dayOfMode) {
    state.dayOfMode = false;
    document.body.classList.remove("day-of-mode");
  }
  $$(".view").forEach((section) =>
    section.classList.toggle("active", section.id === `view-${view}`),
  );
  $$("[data-view]").forEach((button) =>
    button.classList.toggle(
      "active",
      button.dataset.view === view ||
        (view === "meeting" && button.dataset.view === "meetings"),
    ),
  );
  const labels = {
    meetings: "All meetings",
    meeting: currentMeeting()?.book.title || "Meeting",
    books: "Books",
    members: "Members",
    "club-settings": "Settings",
  };
  $("#breadcrumb-page").textContent = labels[view];
  if (view === "meetings") renderMeetings();
  if (view === "books") renderBooks();
  if (view === "members") await loadParticipation();
  if (view === "club-settings") {
    populateClubSettingsForm();
    if (!state.templates.length) await loadTemplates();
  }
};

// The whole card is the attendance button — a tap toggles attendance with an
// immediate optimistic class flip (for a snappy transition) before the save
// resolves and a full re-render settles the roster into its final state.
$("#roster-table").addEventListener("click", async (event) => {
  if (event.target.closest("[data-roster-menu], [data-open-followup]")) return;
  const card = event.target.closest("[data-roster-toggle]");
  if (!card) return;
  const memberId = Number(card.dataset.rosterToggle);
  const entry = state.roster.find((item) => item.member_id === memberId);
  if (!entry) return;
  const nextAttended = !entry.attended;
  card.classList.toggle("is-attended", nextAttended);
  card.setAttribute("aria-pressed", String(nextAttended));
  const statusEl = card.querySelector(".roster-card-status");
  if (statusEl) statusEl.textContent = nextAttended ? "Attended" : "Tap to check in";
  try {
    await saveParticipation(memberId, { attended: nextAttended });
  } catch (error) {
    showToast(error.message);
    await loadSelectedMeeting();
  }
});

$("#roster-table").addEventListener("keydown", (event) => {
  if (event.key !== "Enter" && event.key !== " ") return;
  if (event.target.closest("[data-roster-menu], [data-open-followup]")) return;
  const card = event.target.closest("[data-roster-toggle]");
  if (!card) return;
  event.preventDefault();
  card.click();
});

// Shared by the roster-add search and the transit-label composer's member
// search: renders matching members (excluding any ids in `excludeIds`) as
// clickable result rows into `container`, with an optional "add new
// member" fallback row when nothing matches (or always, if requested).
const renderMemberSearchResults = (container, query, { excludeIds = new Set(), showAddNew = false } = {}) => {
  const trimmed = query.trim();
  if (!trimmed) {
    container.hidden = true;
    container.innerHTML = "";
    return [];
  }
  const lower = trimmed.toLowerCase();
  const matches = state.members
    .filter((member) => !excludeIds.has(member.id))
    .filter((member) => [member.name, member.email].join(" ").toLowerCase().includes(lower))
    .slice(0, 6);
  container.hidden = false;
  const resultsHtml = matches
    .map(
      (member) => `<button class="member-search-result" type="button" data-member-result="${member.id}"><span class="avatar">${escapeHtml(initials(member.name))}</span><div><strong>${escapeHtml(member.name)}</strong><small>${escapeHtml(member.email)}</small></div></button>`,
    )
    .join("");
  const addNewHtml = showAddNew
    ? `<button class="member-search-result member-search-add-new" type="button" data-add-new-member="${escapeHtml(trimmed)}"><svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12h14" /><path d="M12 5v14" /></svg> Add "${escapeHtml(trimmed)}" as a new member</button>`
    : matches.length
      ? ""
      : '<p class="field-help">No matching members.</p>';
  container.innerHTML = resultsHtml + addNewHtml;
  return matches;
};

$("#roster-add-search").addEventListener("input", (event) => {
  renderMemberSearchResults($("#roster-add-results"), event.target.value, {
    excludeIds: new Set(state.roster.map((entry) => entry.member_id)),
    showAddNew: true,
  });
});

$("#roster-add-results").addEventListener("click", async (event) => {
  const addNew = event.target.closest("[data-add-new-member]");
  if (addNew) {
    const name = addNew.dataset.addNewMember;
    $("#roster-add-results").hidden = true;
    return openMemberDialog(null, { addToRoster: true, prefillName: name });
  }
  const resultButton = event.target.closest("[data-member-result]");
  if (!resultButton) return;
  const memberId = Number(resultButton.dataset.memberResult);
  try {
    await request(`/bookclub/meetings/${state.meetingId}/members/${memberId}`, {
      method: "PUT",
      body: JSON.stringify({}),
    });
    $("#roster-add-search").value = "";
    $("#roster-add-results").hidden = true;
    await loadSelectedMeeting();
    showToast("Added to this meeting.");
  } catch (error) {
    showToast(error.message);
  }
});

// Same shape as renderMemberSearchResults, for the Add Meeting book picker.
// No "add new" fallback — books must already exist in the Books section.
const renderBookSearchResults = (container, query) => {
  const trimmed = query.trim();
  if (!trimmed) {
    container.hidden = true;
    container.innerHTML = "";
    return [];
  }
  const lower = trimmed.toLowerCase();
  const matches = state.books
    .filter((book) => [book.title, book.author].join(" ").toLowerCase().includes(lower))
    .slice(0, 6);
  container.hidden = false;
  container.innerHTML = matches.length
    ? matches
        .map(
          (book) => `<button class="member-search-result" type="button" data-book-result="${book.id}"><div><strong>${escapeHtml(book.title)}</strong><small>${escapeHtml(book.author)}</small></div></button>`,
        )
        .join("")
    : '<p class="field-help">No matching books.</p>';
  return matches;
};

$("#meeting-book-search").addEventListener("input", (event) => {
  renderBookSearchResults($("#meeting-book-results"), event.target.value);
});

$("#meeting-book-results").addEventListener("click", (event) => {
  const resultButton = event.target.closest("[data-book-result]");
  if (!resultButton) return;
  const book = state.books.find((entry) => entry.id === Number(resultButton.dataset.bookResult));
  if (!book) return;
  $("#meeting-form").elements.book_id.value = book.id;
  $("#meeting-book-search").value = `${book.title} — ${book.author}`;
  $("#meeting-book-results").hidden = true;
  $("#meeting-book-results").innerHTML = "";
});

$("#member-form").elements.is_new_registrant.addEventListener("change", updateMemberDeliveryFieldVisibility);
$("#member-form").elements.delivery_method.addEventListener("change", updateMemberDeliveryFieldVisibility);

$("#member-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const id = form.elements.id.value;
  const isNewRegistrant = form.elements.is_new_registrant.value === "true";
  const deliveryMethod = isNewRegistrant || id
    ? form.elements.delivery_method.value
    : "none";
  const destinationBranch = form.elements.destination_branch.value.trim();
  if (deliveryMethod === "transfer" && !destinationBranch) {
    $("#member-error").textContent = "Enter a destination branch.";
    return;
  }
  const data = {
    name: form.elements.name.value.trim(),
    email: form.elements.email.value.trim(),
    joined_on: form.elements.joined_on.value,
    active: form.elements.active.value === "true",
    is_new_registrant: isNewRegistrant,
    delivery_method: deliveryMethod,
    destination_branch: deliveryMethod === "transfer" ? destinationBranch : null,
    notes: form.elements.notes.value.trim() || null,
  };
  try {
    const saved = await request(id ? `/bookclub/members/${id}` : "/bookclub/members", {
      method: id ? "PATCH" : "POST",
      body: JSON.stringify(data),
    });
    const shouldAddToRoster = !id && memberDialogAddToRoster && state.meetingId;
    if (shouldAddToRoster) {
      await request(`/bookclub/meetings/${state.meetingId}/members/${saved.id}`, {
        method: "PUT",
        body: JSON.stringify({}),
      });
    }
    $("#member-dialog").close();
    await loadCoreData();
    if (state.view === "members") await loadParticipation();
    showToast(
      id
        ? "Member updated."
        : shouldAddToRoster
          ? "Member added to the club and this meeting."
          : "Member added to the club.",
    );
    if (!id && isNewRegistrant && deliveryMethod === "transfer") {
      if (window.confirm(`Print a transit label for ${data.name} → ${destinationBranch} now?`)) {
        await printTransitLabel(saved.id, destinationBranch);
      }
    }
  } catch (error) {
    $("#member-error").textContent = error.message;
  }
});

$("#delete-member").addEventListener("click", async () => {
  const form = $("#member-form");
  const memberId = Number(form.elements.id.value);
  const member = state.members.find((entry) => entry.id === memberId);
  if (!member) return;
  if (!window.confirm(`Delete ${member.name}? Their roster and reading history will also be removed.`)) return;
  try {
    await request(`/bookclub/members/${memberId}`, { method: "DELETE" });
    $("#member-dialog").close();
    await loadCoreData();
    if (state.view === "members") await loadParticipation();
    showToast("Member deleted.");
  } catch (error) {
    $("#member-error").textContent = error.message;
  }
});

$("#meeting-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const id = form.elements.id.value;
  if (!form.elements.book_id.value) {
    $("#meeting-error").textContent = "Search for and select a book.";
    return;
  }
  const data = {
    book_id: Number(form.elements.book_id.value),
    meeting_date: form.elements.meeting_date.value,
    meeting_time: form.elements.meeting_time.value.trim() || null,
    meeting_duration_minutes: Number(form.elements.meeting_duration_minutes.value),
    location: form.elements.location.value.trim() || null,
    notes: form.elements.notes.value.trim() || null,
  };
  try {
    const saved = await request(
      id ? `/bookclub/meetings/${id}` : "/bookclub/meetings",
      { method: id ? "PATCH" : "POST", body: JSON.stringify(data) },
    );
    state.meetingId = saved.id;
    $("#meeting-dialog").close();
    await loadCoreData();
    await setView("meeting");
    showToast(id ? "Meeting updated." : "Meeting added. Search below to build its roster.");
  } catch (error) {
    $("#meeting-error").textContent = error.message;
  }
});

$("#club-settings-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  try {
    const updated = await request(`/bookclub/clubs/${state.club.id}`, {
      method: "PATCH",
      body: JSON.stringify({
        name: form.elements.name.value.trim(),
        club_type: form.elements.club_type.value,
        description: form.elements.description.value.trim() || null,
        organizer_name: form.elements.organizer_name.value.trim() || null,
        organizer_branch: form.elements.organizer_branch.value.trim() || null,
        video_call_url: form.elements.video_call_url.value.trim() || null,
        public: form.elements.public.value === "true",
      }),
    });
    applyClub(updated);
    showToast("Settings saved.");
  } catch (error) {
    $("#club-settings-error").textContent = error.message;
  }
});

$("#import-book").addEventListener("click", importBookDetails);
$("#book-form").elements.catalogue_url.addEventListener("keydown", (event) => {
  if (event.key !== "Enter") return;
  event.preventDefault();
  importBookDetails();
});

$("#book-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const id = form.elements.id.value;
  const optionalText = [
    "cover_image_url",
    "description",
    "publication_date",
    "isbn",
    "publisher",
    "genres",
    "series",
    "catalogue_url",
    "discussion_notes",
  ];
  const data = {
    title: form.elements.title.value.trim(),
    author: form.elements.author.value.trim(),
    is_past_selection: form.elements.is_past_selection.value === "true",
    page_count: form.elements.page_count.value
      ? Number(form.elements.page_count.value)
      : null,
  };
  optionalText.forEach((field) => {
    data[field] = form.elements[field].value.trim() || null;
  });
  try {
    await request(id ? `/bookclub/books/${id}` : "/bookclub/books", {
      method: id ? "PATCH" : "POST",
      body: JSON.stringify(data),
    });
    $("#book-dialog").close();
    await loadCoreData();
    await setView("books");
    showToast(id ? "Book updated." : "Book added to the collection.");
  } catch (error) {
    $("#book-error").textContent = error.message;
  }
});

$("#participant-note-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const memberId = Number(form.elements.member_id.value);
  try {
    await saveParticipation(
      memberId,
      { notes: form.elements.notes.value.trim() || null },
    );
    $("#participant-note-dialog").close();
    showToast("Participant note saved.");
  } catch (error) {
    $("#participant-note-error").textContent = error.message;
  }
});

$("#send-book-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const memberId = Number(form.elements.member_id.value);
  const destination = form.elements.destination_branch.value.trim();
  const submitButton = form.querySelector('[type="submit"]');
  submitButton.disabled = true;
  $("#send-book-error").textContent = "";
  const printed = await printTransitLabel(memberId, destination);
  submitButton.disabled = false;
  if (printed) {
    $("#send-book-dialog").close();
    showToast("Transit label printed. Member marked as awaiting their book.");
  }
});

$("#template-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const template = state.templates.find((item) => item.key === state.templateKey);
  try {
    await request(`/bookclub/templates/${template.key}`, {
      method: "PATCH",
      body: JSON.stringify({
        name: form.elements.name.value.trim(),
        ...(template.kind === "email"
          ? { subject: form.elements.subject.value.trim() }
          : {}),
        body: form.elements.body.value,
      }),
    });
    await loadTemplates();
    showToast("Template saved.");
  } catch (error) {
    $("#template-error").textContent = error.message;
  }
});

$("#login-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  try {
    const user = await request("/auth/login", {
      method: "POST",
      body: JSON.stringify({
        username: form.elements.username.value,
        password: form.elements.password.value,
      }),
    });
    applyUser(user);
    loginDialog.close();
    await loadClubs();
  } catch (error) {
    $("#login-error").textContent = error.message;
  }
});

$("#club-choice-list").addEventListener("click", async (event) => {
  const choice = event.target.closest("[data-club-id]");
  if (!choice) return;
  try {
    await chooseClub(Number(choice.dataset.clubId));
  } catch (error) {
    $("#club-error").textContent = error.message;
  }
});

$("#club-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  $("#club-error").textContent = "";
  try {
    const club = await request("/bookclub/clubs", {
      method: "POST",
      body: JSON.stringify({
        name: form.elements.name.value.trim(),
        organizer_name: form.elements.organizer_name.value.trim() || null,
        organizer_branch: form.elements.organizer_branch.value.trim() || null,
      }),
    });
    state.clubs.push(club);
    form.reset();
    await chooseClub(club.id);
  } catch (error) {
    $("#club-error").textContent = error.message;
  }
});

document.addEventListener("click", async (event) => {
  const viewButton = event.target.closest("[data-view]");
  if (viewButton) return setView(viewButton.dataset.view);

  const closeButton = event.target.closest("[data-close]");
  if (closeButton) return $(`#${closeButton.dataset.close}`).close();

  const addMeetingButton = event.target.closest("[data-add-meeting]");
  if (addMeetingButton) {
    if (!state.books.length) {
      showToast("Add a book before scheduling its meeting.");
      return setView("books");
    }
    return openMeetingDialog();
  }
  const meetingButton = event.target.closest("[data-open-meeting]");
  if (meetingButton) {
    state.meetingId = Number(meetingButton.dataset.openMeeting);
    await loadSelectedMeeting();
    return setView("meeting");
  }

  const bookMeetingButton = event.target.closest("[data-open-book-meeting]");
  if (bookMeetingButton) {
    state.meetingId = Number(bookMeetingButton.dataset.openBookMeeting);
    $("#book-detail-dialog").close();
    await loadSelectedMeeting();
    return setView("meeting");
  }

  const bookDetailCard = event.target.closest("[data-open-book-detail]");
  if (bookDetailCard && !event.target.closest(".book-card-actions")) {
    return openBookDetail(Number(bookDetailCard.dataset.openBookDetail));
  }

  const editBook = event.target.closest("[data-edit-book]");
  if (editBook) {
    return openBookDialog(
      state.books.find((book) => book.id === Number(editBook.dataset.editBook)),
    );
  }
  const deleteBook = event.target.closest("[data-delete-book]");
  if (deleteBook) {
    const book = state.books.find(
      (entry) => entry.id === Number(deleteBook.dataset.deleteBook),
    );
    if (!window.confirm(`Delete ${book.title} from the book list?`)) return;
    try {
      await request(`/bookclub/books/${book.id}`, { method: "DELETE" });
      await loadCoreData();
      await setView("books");
      return showToast("Book deleted.");
    } catch (error) {
      return showToast(error.message);
    }
  }

  const editMember = event.target.closest("[data-edit-member]");
  if (editMember) {
    return openMemberDialog(
      state.members.find((member) => member.id === Number(editMember.dataset.editMember)),
    );
  }
  const historyButton = event.target.closest("[data-member-history]");
  if (historyButton) return showMemberHistory(Number(historyButton.dataset.memberHistory));
  const jumpBadge = event.target.closest("[data-jump-to-pending]");
  if (jumpBadge) return jumpToPendingMeeting(
    Number(jumpBadge.dataset.jumpToPending),
    jumpBadge.dataset.stage,
  );

  const followupPrompt = event.target.closest("[data-open-followup]");
  if (followupPrompt) {
    return openFollowupDialog(
      Number(followupPrompt.dataset.openFollowup),
      followupPrompt.dataset.stage,
    );
  }

  const sendBookButton = event.target.closest("[data-send-book]");
  if (sendBookButton) {
    sendBookButton.closest("[data-roster-menu]")?.removeAttribute("open");
    const memberId = Number(sendBookButton.dataset.sendBook);
    const member = state.members.find((entry) => entry.id === memberId);
    if (!member) return;
    const form = $("#send-book-form");
    form.reset();
    form.elements.member_id.value = memberId;
    form.elements.destination_branch.value = member.destination_branch || "";
    $("#send-book-title").textContent = `Send a book to ${member.name}`;
    $("#send-book-context").textContent = `Prepare a transit label for ${member.name}'s copy of ${currentMeeting()?.book.title || "this month's book"}.`;
    $("#send-book-error").textContent = "";
    return $("#send-book-dialog").showModal();
  }

  const participantNoteButton = event.target.closest("[data-participant-note]");
  if (participantNoteButton) {
    participantNoteButton.closest("[data-roster-menu]")?.removeAttribute("open");
    const memberId = Number(participantNoteButton.dataset.participantNote);
    const entry = state.roster.find((item) => item.member_id === memberId);
    if (!entry) return;
    const form = $("#participant-note-form");
    form.reset();
    form.elements.member_id.value = memberId;
    form.elements.notes.value = entry.notes || "";
    $("#participant-note-title").textContent = `${entry.member.name} — session note`;
    $("#participant-note-error").textContent = "";
    return $("#participant-note-dialog").showModal();
  }

  const templateButton = event.target.closest("[data-template-key]");
  if (templateButton) {
    state.templateKey = templateButton.dataset.templateKey;
    return renderTemplates();
  }
  const variableButton = event.target.closest("[data-variable]");
  if (variableButton) {
    const textarea = $("#template-form").elements.body;
    const token = `{{${variableButton.dataset.variable}}}`;
    textarea.setRangeText(token, textarea.selectionStart, textarea.selectionEnd, "end");
    return textarea.focus();
  }

  const removeFromRosterButton = event.target.closest("[data-remove-from-roster]");
  if (removeFromRosterButton) {
    const memberId = Number(removeFromRosterButton.dataset.removeFromRoster);
    try {
      await request(`/bookclub/meetings/${state.meetingId}/members/${memberId}`, {
        method: "DELETE",
      });
      await loadSelectedMeeting();
      return showToast("Removed from the roster.");
    } catch (error) {
      return showToast(error.message);
    }
  }

  const copyEmailButton = event.target.closest("[data-copy-email]");
  if (copyEmailButton) {
    try {
      await navigator.clipboard.writeText(copyEmailButton.dataset.copyEmail);
      return showToast("Email address copied.");
    } catch (error) {
      return showToast("Could not copy email address.");
    }
  }

  const copyRegistrantButton = event.target.closest("[data-copy-registrant-email]");
  if (copyRegistrantButton) {
    const memberId = Number(copyRegistrantButton.dataset.copyRegistrantEmail);
    const endpoint = copyRegistrantButton.dataset.stage === "arrival" ? "arrival-email" : "onboarding-email";
    try {
      const rendered = await request(
        `/bookclub/meetings/${state.meetingId}/members/${memberId}/${endpoint}/preview`,
        { method: "POST" },
      );
      const member = state.members.find((entry) => entry.id === memberId);
      await navigator.clipboard.writeText(
        `To: ${member?.email || ""}\nSubject: ${rendered.subject}\n\n${rendered.body}`,
      );
      return showToast("Email copied.");
    } catch (error) {
      return showToast(error.message);
    }
  }

  const markSentButton = event.target.closest("[data-mark-registrant-sent]");
  if (markSentButton) {
    const memberId = Number(markSentButton.dataset.markRegistrantSent);
    const stage = markSentButton.dataset.stage;
    const endpoint = stage === "arrival" ? "arrival-email" : "onboarding-email";
    const rosterEntry = state.roster.find((entry) => entry.member_id === memberId);
    const member = rosterEntry?.member;
    const alreadySentAt = stage === "arrival" ? member?.arrival_email_sent_at : member?.onboarding_email_sent_at;
    if (
      alreadySentAt &&
      !window.confirm(`This email was already marked sent on ${formatDate(alreadySentAt.slice(0, 10))} — mark it sent again?`)
    ) {
      return;
    }
    try {
      await request(
        `/bookclub/meetings/${state.meetingId}/members/${memberId}/${endpoint}/mark-sent`,
        { method: "POST" },
      );
      await refreshMember(memberId);
      renderMembers();
      renderRoster();
      renderPostMeetingRecap();
      if ($("#followup-dialog").open) $("#followup-dialog").close();
      return showToast("Marked as sent.");
    } catch (error) {
      return showToast(error.message);
    }
  }

  const sendRegistrantButton = event.target.closest("[data-send-registrant-email]");
  if (sendRegistrantButton) {
    const memberId = Number(sendRegistrantButton.dataset.sendRegistrantEmail);
    const stage = sendRegistrantButton.dataset.stage;
    const endpoint = stage === "arrival" ? "arrival-email" : "onboarding-email";
    const rosterEntry = state.roster.find((entry) => entry.member_id === memberId);
    const member = rosterEntry?.member;
    const alreadySentAt = stage === "arrival" ? member?.arrival_email_sent_at : member?.onboarding_email_sent_at;
    if (
      alreadySentAt &&
      !window.confirm(`This email was already sent on ${formatDate(alreadySentAt.slice(0, 10))} — send again?`)
    ) {
      return;
    }
    try {
      const result = await request(
        `/bookclub/meetings/${state.meetingId}/members/${memberId}/${endpoint}/send`,
        { method: "POST" },
      );
      await refreshMember(memberId);
      renderMembers();
      renderRoster();
      renderPostMeetingRecap();
      if ($("#followup-dialog").open) $("#followup-dialog").close();
      return showToast(
        result.sent ? "Email sent." : "Email delivery isn't configured — use Copy instead.",
      );
    } catch (error) {
      return showToast(error.message);
    }
  }
});

$("#member-search").addEventListener("input", (event) => {
  state.memberQuery = event.target.value;
  renderMembers();
});
$("#member-sort").addEventListener("change", (event) => {
  state.memberSort = event.target.value;
  renderMembers();
});
$("#meeting-search").addEventListener("input", (event) => {
  state.meetingQuery = event.target.value;
  renderMeetings();
});
$("#book-search").addEventListener("input", (event) => {
  state.bookQuery = event.target.value;
  renderBooks();
});
$("#book-unscheduled-filter").addEventListener("change", (event) => {
  state.bookUnscheduledOnly = event.target.checked;
  renderBooks();
});
$("#book-sort").addEventListener("change", (event) => {
  state.bookSort = event.target.value;
  renderBooks();
});
$$('[data-book-display]').forEach((button) => {
  button.addEventListener("click", () => {
    state.bookDisplay = button.dataset.bookDisplay;
    renderBooks();
  });
});
$("#add-member").addEventListener("click", () => openMemberDialog());
const openDefaultMeeting = async () => {
  state.meetingId = chooseDefaultMeeting();
  await loadSelectedMeeting();
  await setView(state.meetingId ? "meeting" : "meetings");
};
$("#open-next-meeting").addEventListener("click", openDefaultMeeting);
$("#add-book").addEventListener("click", () => openBookDialog());
$("#book-list").addEventListener("click", (event) => {
  if (event.target.closest("#empty-add-book")) openBookDialog();
});
$("#book-list").addEventListener("keydown", (event) => {
  if (!["Enter", " "].includes(event.key) || event.target.closest(".book-card-actions")) return;
  const card = event.target.closest("[data-open-book-detail]");
  if (!card || event.target !== card) return;
  event.preventDefault();
  openBookDetail(Number(card.dataset.openBookDetail));
});
$("#book-detail-edit").addEventListener("click", () => {
  const book = state.books.find((entry) => entry.id === state.bookDetailId);
  if (!book) return;
  $("#book-detail-dialog").close();
  openBookDialog(book);
});
$("#book-detail-previous").addEventListener("click", (event) => {
  if (event.currentTarget.dataset.bookId) openBookDetail(Number(event.currentTarget.dataset.bookId));
});
$("#book-detail-next").addEventListener("click", (event) => {
  if (event.currentTarget.dataset.bookId) openBookDetail(Number(event.currentTarget.dataset.bookId));
});
$("#edit-meeting").addEventListener("click", () => openMeetingDialog(currentMeeting()));
$("#delete-meeting").addEventListener("click", async () => {
  const meeting = currentMeeting();
  if (!meeting) return;
  if (
    !window.confirm(
      `Delete the ${formatDate(meeting.meeting_date)} meeting for ${meeting.book.title}? Attendance, participant notes, discussion notes, and the giveaway winner will also be deleted.`,
    )
  ) {
    return;
  }
  const deleteButton = $("#delete-meeting");
  deleteButton.disabled = true;
  deleteButton.textContent = "Deleting…";
  $("#meeting-error").textContent = "";
  try {
    await request(`/bookclub/meetings/${meeting.id}`, { method: "DELETE" });
    $("#meeting-dialog").close();
    state.meetings = state.meetings.filter(
      (entry) => entry.id !== meeting.id,
    );
    state.meetingId = chooseDefaultMeeting();
    state.roster = [];
    renderMeetings();
    renderMeetingView();
    await setView("meetings");
    showToast("Meeting deleted.");
  } catch (error) {
    $("#meeting-error").textContent = error.message;
  } finally {
    deleteButton.disabled = false;
    deleteButton.textContent = "Delete meeting";
  }
});
const openMeetingById = async (meetingId) => {
  if (!meetingId) return;
  state.meetingId = Number(meetingId);
  await loadSelectedMeeting();
  // Previous/Next always land on the session workspace, even for an
  // archived meeting — the archive summary is reached deliberately, by
  // clicking the program from the meetings page (see the
  // data-open-meeting handler), not by paging through sessions.
  state.viewingEdit = true;
  renderMeetingView();
  await setView("meeting");
};

$("#previous-meeting").addEventListener("click", (event) =>
  openMeetingById(event.currentTarget.dataset.meetingId),
);
$("#next-meeting").addEventListener("click", (event) =>
  openMeetingById(event.currentTarget.dataset.meetingId),
);
$("#toggle-completed").addEventListener("click", async (event) => {
  const meeting = currentMeeting();
  if (!meeting) return;
  const completing = meeting.status !== "completed";
  event.target.disabled = true;
  try {
    const updated = await request(`/bookclub/meetings/${meeting.id}`, {
      method: "PATCH",
      body: JSON.stringify({
        status: completing ? "completed" : "planned",
        archived_at: completing ? new Date().toISOString() : null,
      }),
    });
    const index = state.meetings.findIndex((entry) => entry.id === updated.id);
    state.meetings[index] = updated;
    renderMeetings();
    renderMeetingView();
    showToast(
      completing ? "Meeting marked completed and archived." : "Session reopened.",
    );
  } catch (error) {
    showToast(error.message);
  } finally {
    event.target.disabled = false;
  }
});
$("#day-of-mode").addEventListener("click", () => {
  const meeting = currentMeeting();
  if (!meeting) return;
  state.dayOfMode = !state.dayOfMode;
  document.body.classList.toggle("day-of-mode", state.dayOfMode);
  renderMeetingView();
});
$("#edit-session").addEventListener("click", () => {
  state.viewingEdit = true;
  renderMeetingView();
});
$("#discussion-notes").addEventListener("input", () => {
  state.discussionNotesDirty = true;
  $("#discussion-notes-status").textContent = "Unsaved changes";
});
$("#save-discussion-notes").addEventListener("click", async () => {
  const meeting = currentMeeting();
  if (!meeting) return showToast("Add a meeting first.");
  const button = $("#save-discussion-notes");
  button.disabled = true;
  try {
    const updated = await request(`/bookclub/meetings/${meeting.id}`, {
      method: "PATCH",
      body: JSON.stringify({
        discussion_notes: $("#discussion-notes").value.trim() || null,
      }),
    });
    const index = state.meetings.findIndex((entry) => entry.id === updated.id);
    state.meetings[index] = updated;
    state.discussionNotesDirty = false;
    renderDiscussionNotes();
    renderPostMeetingRecap();
    showToast("Discussion notes saved.");
  } catch (error) {
    showToast(error.message);
  } finally {
    button.disabled = false;
  }
});
$("#copy-session-recap").addEventListener("click", async () => {
  const recap = sessionRecapText();
  if (!recap) return showToast("Add a meeting first.");
  await navigator.clipboard.writeText(recap);
  showToast("Session recap copied.");
});
$("#toggle-session-recap").addEventListener("click", () => {
  const expanded = $("#toggle-session-recap").getAttribute("aria-expanded") === "true";
  setSessionRecapExpanded(!expanded);
});
$("#open-reminder-dialog").addEventListener("click", () => {
  if (!currentMeeting()) return showToast("Add a meeting first.");
  renderReminderPanel();
  $("#reminder-dialog").showModal();
});
$("#open-giveaway-dialog").addEventListener("click", openGiveawayDialog);
$("#copy-reminder-list").addEventListener("click", async () => {
  const emails = state.roster.map((entry) => entry.member.email);
  if (!emails.length) return showToast("No one is on this meeting's roster yet.");
  await navigator.clipboard.writeText(emails.join("; "));
  showToast("Address list copied.");
});
$("#copy-reminder-text").addEventListener("click", async () => {
  const meeting = currentMeeting();
  if (!meeting) return showToast("Add a meeting first.");
  try {
    const rendered = await request(
      "/bookclub/meetings/" + meeting.id + "/reminder/preview",
      { method: "POST" },
    );
    const emailText = rendered.subject
      ? "Subject: " + rendered.subject + "\n\n" + rendered.body
      : rendered.body;
    await navigator.clipboard.writeText(emailText);
    showToast("Reminder email text copied.");
  } catch (error) {
    showToast(error.message);
  }
});
$("#send-reminder").addEventListener("click", async () => {
  const meeting = currentMeeting();
  if (!meeting) return showToast("Add a meeting first.");
  const memberIds = state.roster.map((entry) => entry.member_id);
  if (!memberIds.length) return showToast("No one is on this meeting's roster yet.");
  if (
    meeting.reminder_sent_at &&
    !window.confirm(`Reminder already sent on ${formatDate(meeting.reminder_sent_at.slice(0, 10))} — send again?`)
  ) {
    return;
  }
  try {
    const result = await request(`/bookclub/meetings/${meeting.id}/reminder/send`, {
      method: "POST",
      body: JSON.stringify({ member_ids: memberIds }),
    });
    await refreshCurrentMeeting();
    renderReminderPanel();
    showToast(
      result.sent
        ? `Reminder sent to ${result.recipient_count} people.`
        : "Email delivery isn't configured — copy the list instead.",
    );
  } catch (error) {
    showToast(error.message);
  }
});
$("#mark-reminder-sent").addEventListener("click", async () => {
  const meeting = currentMeeting();
  if (!meeting) return showToast("Add a meeting first.");
  if (
    meeting.reminder_sent_at &&
    !window.confirm(`Reminder already marked sent on ${formatDate(meeting.reminder_sent_at.slice(0, 10))} — mark it sent again?`)
  ) {
    return;
  }
  try {
    await request(`/bookclub/meetings/${meeting.id}/reminder/mark-sent`, { method: "POST" });
    await refreshCurrentMeeting();
    renderReminderPanel();
    showToast("Reminder marked as sent.");
  } catch (error) {
    showToast(error.message);
  }
});
$("#restore-template").addEventListener("click", async () => {
  if (!state.templateKey || !window.confirm("Restore the original wording for this template?")) return;
  await request(`/bookclub/templates/${state.templateKey}/restore`, { method: "POST" });
  await loadTemplates();
  showToast("Default wording restored.");
});
$("#logout-button").addEventListener("click", async () => {
  await request("/auth/logout", { method: "POST" });
  state.club = null;
  showLogin();
});

document.addEventListener("click", (event) => {
  if (accountMenu.open && !accountMenu.contains(event.target)) {
    accountMenu.open = false;
  }
  $$(".roster-card-menu[open]").forEach((menu) => {
    if (!menu.contains(event.target)) menu.open = false;
  });
});

document.addEventListener("keydown", (event) => {
  if (event.key !== "Escape") return;
  accountMenu.open = false;
  $$(".roster-card-menu[open]").forEach((menu) => { menu.open = false; });
});

$("#switch-club").addEventListener("click", showClubPicker);

const initialize = async () => {
  try {
    const user = await request("/auth/me");
    applyUser(user);
    await loadClubs();
  } catch (error) {
    if (error.status !== 401) showToast(error.message);
  }
};

initialize();

// "In progress" is time-computed, not stored — recheck periodically so a
// meeting flips live for anyone with the tab open through its start time,
// without needing a manual refresh.
setInterval(() => {
  if (state.view === "meeting") renderSessionControls();
}, 60000);
