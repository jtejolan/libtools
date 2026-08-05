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
  questions: [],
  templates: [],
  templateKey: null,
  participation: [],
  participationSort: { key: "name", dir: 1 },
  transitSelectedMemberId: null,
  bookUnscheduledOnly: false,
  rosterQuery: "",
  memberQuery: "",
  meetingQuery: "",
  bookQuery: "",
};
let pendingDashboardAction = new URLSearchParams(window.location.search).get("action");

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

const openClubSettingsDialog = () => {
  const club = state.club;
  if (!club) return showToast("Choose a club first.");
  const form = $("#club-settings-form");
  form.reset();
  form.elements.name.value = club.name || "";
  form.elements.description.value = club.description || "";
  form.elements.organizer_name.value = club.organizer_name || "";
  form.elements.organizer_branch.value = club.organizer_branch || "";
  form.elements.video_call_url.value = club.video_call_url || "";
  form.elements.public.value = String(club.public ?? true);
  $("#club-settings-error").textContent = "";
  $("#club-settings-dialog").showModal();
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
  url.searchParams.delete("action");
  window.history.replaceState({}, "", `${url.pathname}${url.search}${url.hash}`);
};

const runDashboardAction = async () => {
  if (!pendingDashboardAction || !state.club) return;
  const action = pendingDashboardAction;
  finishDashboardAction();
  if (action === "add-member") {
    await setView("members");
    openMemberDialog();
  } else if (action === "add-book") {
    await setView("books");
    openBookDialog();
  }
};

const chooseClub = async (clubId) => {
  const club = await request(`/bookclub/clubs/${clubId}/select`, { method: "POST" });
  applyClub(club);
  clubDialog.close();
  await loadCoreData();
  await setView("meetings");
  await runDashboardAction();
};

const loadClubs = async () => {
  state.clubs = await request("/bookclub/clubs");
  if (!state.clubs.length) return showClubPicker();
  let selected = null;
  try {
    selected = await request("/bookclub/clubs/selected");
  } catch (error) {
    if (error.status !== 404) throw error;
  }
  if (selected && state.clubs.some((club) => club.id === selected.id)) {
    applyClub(selected);
    await loadCoreData();
    await setView("meetings");
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

const chooseDefaultMeeting = () => {
  if (!state.meetings.length) return null;
  const upcoming = state.meetings
    .filter((meeting) => meeting.meeting_date >= today())
    .sort((a, b) => a.meeting_date.localeCompare(b.meeting_date));
  return upcoming[0]?.id || state.meetings[0].id;
};

const loadCoreData = async () => {
  const [members, books, meetings] = await Promise.all([
    request("/bookclub/members?limit=500"),
    request("/bookclub/books?limit=500"),
    request("/bookclub/meetings?limit=500"),
  ]);
  state.members = members;
  state.books = books;
  state.meetings = meetings;
  if (!state.meetings.some((meeting) => meeting.id === state.meetingId)) {
    state.meetingId = chooseDefaultMeeting();
  }
  renderMeetings();
  renderBooks();
  renderMembers();
  await loadSelectedMeeting();
};

const loadSelectedMeeting = async () => {
  if (!state.meetingId) {
    state.roster = [];
    state.questions = [];
    renderMeetingView();
    return;
  }
  [state.roster, state.questions] = await Promise.all([
    request(`/bookclub/meetings/${state.meetingId}/roster`),
    request(`/bookclub/meetings/${state.meetingId}/questions`),
  ]);
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
  const list = $("#meeting-list");
  if (!meetings.length) {
    list.innerHTML = `<div class="empty-collection"><span>◫</span><h2>${query ? "No matching meetings" : "No meetings yet"}</h2><p>${query ? "Try a different search." : "Add the first meeting after creating a book for the club."}</p>${query ? "" : '<button class="primary-button" type="button" data-add-meeting>＋ Add meeting</button>'}</div>`;
    return;
  }
  list.innerHTML = meetings
    .map(
      (meeting) => `<button class="meeting-card" type="button" data-open-meeting="${meeting.id}"><div class="meeting-date">${escapeHtml(
        new Intl.DateTimeFormat("en-CA", { month: "short", day: "numeric" }).format(
          new Date(`${meeting.meeting_date}T12:00:00`),
        ),
      )}<span>${escapeHtml(String(new Date(`${meeting.meeting_date}T12:00:00`).getFullYear()))}</span></div><div><h2>${escapeHtml(meeting.book.title)}</h2><p>by ${escapeHtml(meeting.book.author)}${meeting.location ? ` · ${escapeHtml(meeting.location)}` : ""}</p></div><span class="card-arrow">→</span></button>`,
    )
    .join("");
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
  $("#book-stat-total").textContent = books.length;
  $("#book-stat-meetings").textContent = state.meetings.filter(
    (meeting) => meeting.meeting_date <= today(),
  ).length;
  const withPages = books.filter((book) => book.page_count);
  const avgPages = withPages.length
    ? Math.round(withPages.reduce((sum, book) => sum + book.page_count, 0) / withPages.length)
    : null;
  $("#book-stat-avg-pages").textContent = avgPages ?? "—";
  const longest = withPages.reduce(
    (max, book) => (!max || book.page_count > max.page_count ? book : max),
    null,
  );
  $("#book-stat-longest").textContent = longest ? `${longest.page_count}p` : "—";
  const genreCounts = new Map();
  books.forEach((book) => {
    (book.genres || "")
      .split(",")
      .map((genre) => genre.trim())
      .filter(Boolean)
      .forEach((genre) => genreCounts.set(genre, (genreCounts.get(genre) || 0) + 1));
  });
  const topGenres = [...genreCounts.entries()].sort((a, b) => b[1] - a[1]).slice(0, 3);
  $("#book-genre-breakdown").textContent = topGenres.length
    ? `Top genres: ${topGenres.map(([genre, count]) => `${genre} (${count})`).join(", ")}`
    : "";
};

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
    books = books.filter((book) => !scheduled.has(book.id));
  }
  $("#book-count").textContent = `${state.books.length} ${state.books.length === 1 ? "book" : "books"}`;
  renderBookStats();
  const list = $("#book-list");
  if (!books.length) {
    list.innerHTML = `<div class="empty-collection"><span>▥</span><h2>${query || state.bookUnscheduledOnly ? "No matching books" : "Your book list is empty"}</h2><p>${query || state.bookUnscheduledOnly ? "Try a different title, author, ISBN, or genre." : "Add the first title selected for the club."}</p>${query || state.bookUnscheduledOnly ? "" : '<button class="primary-button" id="empty-add-book" type="button">＋ Add book</button>'}</div>`;
    return;
  }
  list.innerHTML = books
    .map((book) => {
      const cover = safeImageUrl(book.cover_image_url);
      const publicationYear = book.publication_date?.slice(0, 4);
      const unscheduled = !scheduled.has(book.id);
      return `<article class="book-card">${unscheduled ? '<span class="status-pill unscheduled-badge">Not yet scheduled</span>' : ""}<div class="book-cover">${cover ? `<img src="${escapeHtml(cover)}" alt="Cover of ${escapeHtml(book.title)}" loading="lazy" />` : escapeHtml(initials(book.title))}</div><div class="book-card-copy"><h2>${escapeHtml(book.title)}</h2><p class="book-author">${escapeHtml(book.author)}</p><p class="book-description">${escapeHtml(book.description || "No description has been added yet.")}</p><div class="book-meta">${publicationYear ? `<span>${escapeHtml(publicationYear)}</span>` : ""}${book.page_count ? `<span>${book.page_count} pages</span>` : ""}${book.genres ? `<span>${escapeHtml(book.genres)}</span>` : ""}</div></div><div class="book-card-actions"><button type="button" data-edit-book="${book.id}">Edit</button><button class="danger-text" type="button" data-delete-book="${book.id}">Delete</button></div></article>`;
    })
    .join("");
};

const renderMeetingView = () => {
  const meeting = currentMeeting();
  $("#edit-meeting").disabled = !meeting;
  const cover = $("#meeting-cover");
  cover.hidden = !meeting;
  if (!meeting) {
    $("#meeting-heading").textContent = "Add your first meeting";
    $("#meeting-intro").textContent =
      "Set the next book and date, then search below to build its roster.";
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
  $("#roster-add-search").value = "";
  $("#roster-add-results").hidden = true;
  renderRoster();
  renderGiveaway();
  renderQuestions();
  renderWelcomeEmails();
  renderReminderPanel();
};

const renderRoster = () => {
  const body = $("#roster-table");
  if (!state.meetingId) {
    body.innerHTML = '<tr><td colspan="3" class="empty-cell">Add a meeting to start building its roster.</td></tr>';
    return;
  }
  const query = state.rosterQuery.trim().toLowerCase();
  const entries = state.roster.filter((entry) =>
    [entry.member.name, entry.member.email]
      .join(" ")
      .toLowerCase()
      .includes(query),
  );
  if (!entries.length) {
    body.innerHTML = `<tr><td colspan="3" class="empty-cell">${query ? "No matching members." : "No one has been added to this meeting yet — search above to add someone."}</td></tr>`;
    return;
  }
  body.innerHTML = entries
    .map((entry) => {
      const member = entry.member;
      return `<tr data-member-id="${member.id}">
        <td><div class="member-cell" title="${escapeHtml(member.notes || "")}"><span class="avatar">${escapeHtml(initials(member.name))}</span><div><strong>${escapeHtml(member.name)}</strong><small>${escapeHtml(member.email)}</small></div></div></td>
        <td><label class="check-wrap"><input type="checkbox" data-roster-field="attended" ${entry.attended ? "checked" : ""} /><span>${entry.attended ? "Yes" : "No"}</span></label></td>
        <td><button class="row-action danger-text" type="button" data-remove-from-roster="${member.id}">Remove</button></td>
      </tr>`;
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
  renderMeetingView();
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
    content.innerHTML = `<div class="giveaway-orbit"><span>★</span></div><p class="winner-name">${escapeHtml(winner.name)}</p><p>Monthly book giveaway winner</p><button class="secondary-button" id="draw-winner" type="button">Draw again</button>`;
  } else {
    content.innerHTML = '<div class="giveaway-orbit"><span>★</span></div><p>Draw one name at random from everyone marked as attended.</p><button class="primary-button" id="draw-winner" type="button">Draw a name</button>';
  }
  $("#draw-winner").addEventListener("click", drawWinner);
};

const drawWinner = async () => {
  const meeting = currentMeeting();
  if (!meeting) return showToast("Add a meeting first.");
  const redraw = Boolean(meeting.giveaway_winner_member_id);
  if (redraw && !window.confirm("Replace the saved giveaway winner?")) return;
  try {
    const result = await request(
      `/bookclub/meetings/${meeting.id}/giveaway/draw${redraw ? "?redraw=true" : ""}`,
      { method: "POST" },
    );
    meeting.giveaway_winner_member_id = result.member.id;
    renderGiveaway();
    showToast(`${result.member.name} wins this month’s book!`);
  } catch (error) {
    showToast(error.message);
  }
};

const renderQuestions = () => {
  const list = $("#question-list");
  if (!state.questions.length) {
    list.innerHTML = '<li class="empty-inline">No questions added yet.</li>';
    return;
  }
  list.innerHTML = state.questions
    .map(
      (question) => `<li>${escapeHtml(question.text)}<span class="question-actions"><button type="button" data-edit-question="${question.id}" aria-label="Edit question">✎</button><button type="button" data-delete-question="${question.id}" aria-label="Delete question">×</button></span></li>`,
    )
    .join("");
};

const DELIVERY_LABELS = { none: "No copy", pickup: "Pickup at PBRL", transfer: "Send to branch" };

// A new registrant needs one or two emails over their lifetime: the
// welcome email (always), then — only for a transfer — a follow-up once
// the book actually lands at the destination branch. Both are one-time
// sends tracked on the member, gated by whichever meeting they're on this
// roster for (so book_title/date have somewhere to come from).
const registrantEmailStage = (member) => {
  if (!member.onboarding_email_sent_at) return "welcome";
  if (member.delivery_method === "transfer" && !member.arrival_email_sent_at) return "arrival";
  return null;
};

const STAGE_LABELS = {
  welcome: "Needs welcome email",
  arrival: "Needs arrival confirmation",
};

const renderWelcomeEmails = () => {
  const container = $("#welcome-list");
  const rows = state.roster
    .filter((entry) => entry.member.is_new_registrant)
    .map((entry) => ({ entry, stage: registrantEmailStage(entry.member) }))
    .filter((row) => row.stage);
  if (!rows.length) {
    container.innerHTML = '<div class="empty-card"><span>✉</span><p>No new registrants need an email right now.</p></div>';
    return;
  }
  container.innerHTML = rows
    .map(({ entry, stage }) => {
      const member = entry.member;
      const badgeDetail =
        stage === "arrival" && member.destination_branch ? ` — ${escapeHtml(member.destination_branch)}` : "";
      return `<article class="welcome-row">
        <div class="member-cell"><span class="avatar">${escapeHtml(initials(member.name))}</span><div><strong>${escapeHtml(member.name)}</strong><small>${escapeHtml(member.email)}</small></div></div>
        <span class="status-pill ${stage === "arrival" ? "arrival-badge" : ""}">${escapeHtml(STAGE_LABELS[stage])}${badgeDetail}</span>
        <div class="welcome-row-actions">
          <button class="quiet-button" type="button" data-copy-registrant-email="${member.id}" data-stage="${stage}">Copy</button>
          <button class="primary-button" type="button" data-send-registrant-email="${member.id}" data-stage="${stage}">Send</button>
        </div>
      </article>`;
    })
    .join("");
};

const renderReminderPanel = () => {
  const meeting = currentMeeting();
  const status = $("#reminder-status");
  const countEl = $("#reminder-recipient-count");
  if (!meeting) {
    status.textContent = "Add a meeting first.";
    countEl.textContent = "";
    return;
  }
  status.textContent = meeting.reminder_sent_at
    ? `Reminder sent on ${formatDate(meeting.reminder_sent_at.slice(0, 10))}.`
    : "Not sent yet.";
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

const memberPendingBadge = (member) => {
  if (member.is_new_registrant && !member.onboarding_email_sent_at) {
    return { label: "Needs welcome email", className: "new-badge" };
  }
  if (
    member.is_new_registrant &&
    member.delivery_method === "transfer" &&
    !member.arrival_email_sent_at
  ) {
    return {
      label: `Needs arrival confirmation${member.destination_branch ? ` — ${member.destination_branch}` : ""}`,
      className: "arrival-badge",
    };
  }
  return null;
};

const renderMembers = () => {
  const query = state.memberQuery.trim().toLowerCase();
  const members = state.members.filter((member) =>
    [member.name, member.email].join(" ").toLowerCase().includes(query),
  );
  $("#member-count").textContent = `${state.members.filter((member) => member.active).length} active · ${state.members.length} total`;
  $("#members-table").innerHTML = members.length
    ? members
        .map((member) => {
          const badge = memberPendingBadge(member);
          const badgeHtml = badge
            ? `<button class="status-pill ${badge.className} jump-badge" type="button" data-jump-to-pending="${member.id}">${escapeHtml(badge.label)}</button>`
            : "";
          return `<tr><td><div class="member-cell" title="${escapeHtml(member.notes || "")}"><span class="avatar">${escapeHtml(initials(member.name))}</span><div><strong>${escapeHtml(member.name)}</strong><small>${escapeHtml(member.email)}</small>${badgeHtml}</div></div></td><td>${escapeHtml(formatDate(member.joined_on))}</td><td><span class="status-pill ${member.active ? "" : "inactive"}">${member.active ? "Active" : "Inactive"}</span></td><td><button class="row-action" type="button" data-member-history="${member.id}">View history</button></td><td><button class="row-action" type="button" data-edit-member="${member.id}">Edit</button></td></tr>`;
        })
        .join("")
    : '<tr><td colspan="5" class="empty-cell">No matching members.</td></tr>';
};

const jumpToPendingMeeting = async (memberId) => {
  try {
    const history = await request(`/bookclub/members/${memberId}/history`);
    const targetMeeting = history[0]?.meeting;
    if (!targetMeeting) return showToast("No meeting found for this registrant.");
    state.meetingId = targetMeeting.id;
    await loadSelectedMeeting();
    await setView("messages");
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
  form.elements.is_new_registrant.checked = member ? Boolean(member.is_new_registrant) : true;
  form.elements.delivery_method.value = member?.delivery_method || "none";
  form.elements.destination_branch.value = member?.destination_branch || "";
  form.elements.notes.value = member?.notes || "";
  updateMemberDeliveryFieldVisibility();
  $("#member-dialog-title").textContent = member ? "Edit member" : "Add member";
  $("#member-error").textContent = "";
  $("#member-dialog").showModal();
};

const updateMemberDeliveryFieldVisibility = () => {
  const form = $("#member-form");
  const isNewRegistrant = form.elements.is_new_registrant.checked;
  $("#member-delivery-field").hidden = !isNewRegistrant;
  $("#member-branch-field").hidden =
    !isNewRegistrant || form.elements.delivery_method.value !== "transfer";
};

const openMeetingDialog = (meeting = null) => {
  const form = $("#meeting-form");
  form.reset();
  form.elements.book_id.innerHTML = state.books.length
    ? state.books
        .map(
          (book) => `<option value="${book.id}">${escapeHtml(book.title)} — ${escapeHtml(book.author)}</option>`,
        )
        .join("")
    : '<option value="">Add a book first</option>';
  form.elements.id.value = meeting?.id || "";
  form.elements.book_id.value = meeting?.book_id || state.books[0]?.id || "";
  form.elements.meeting_date.value = meeting?.meeting_date || today();
  form.elements.meeting_time.value = meeting?.meeting_time || "";
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
  $("#history-title").textContent = `${member.name}’s history`;
  const deliveryHtml = member.is_new_registrant
    ? `<p class="history-notes">${escapeHtml(DELIVERY_LABELS[member.delivery_method] || member.delivery_method)}${member.delivery_method === "transfer" && member.destination_branch ? ` — ${escapeHtml(member.destination_branch)}` : ""}</p>`
    : "";
  const notesHtml = member.notes
    ? `<p class="history-notes">${escapeHtml(member.notes)}</p>`
    : "";
  $("#history-content").innerHTML = deliveryHtml + notesHtml + (history.length
    ? `<div class="history-list">${history
        .map(
          (entry) => `<article class="history-row"><div><strong>${escapeHtml(entry.meeting.book.title)}</strong><small>${escapeHtml(formatDate(entry.meeting.meeting_date))}</small></div><span class="history-mark ${entry.attended ? "yes" : "no"}">${entry.attended ? "Attended ✓" : "Absent"}</span></article>`,
        )
        .join("")}</div>`
    : '<div class="empty-card"><p>No meeting history yet.</p></div>');
  $("#history-dialog").showModal();
};

const printTransitLabel = async (memberId, destinationBranch) => {
  try {
    const rendered = await request("/bookclub/transit-labels/render", {
      method: "POST",
      body: JSON.stringify({ member_id: memberId, destination_branch: destinationBranch }),
    });
    $("#print-sheet").innerHTML = `<article class="print-label">${escapeHtml(rendered.body)}</article>`;
    window.print();
  } catch (error) {
    showToast(error.message);
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
  renderParticipation();
};

const participationSortValue = (row, key) => {
  switch (key) {
    case "name":
      return row.member.name.toLowerCase();
    case "last_attended_date":
      return row.last_attended_date || "";
    case "last_contacted_at":
      return row.last_contacted_at || "";
    default:
      return row[key] ?? 0;
  }
};

const renderParticipation = () => {
  const { key, dir } = state.participationSort;
  const rows = [...state.participation].sort((a, b) => {
    const valueA = participationSortValue(a, key);
    const valueB = participationSortValue(b, key);
    if (valueA < valueB) return -1 * dir;
    if (valueA > valueB) return 1 * dir;
    return 0;
  });
  $("#participation-count").textContent = `${rows.length} ${rows.length === 1 ? "member" : "members"}`;
  $("#participation-table").innerHTML = rows.length
    ? rows
        .map((row) => {
          const member = row.member;
          const lapsed = row.meetings_since_last_attended >= 3;
          return `<tr class="${lapsed ? "lapsed-row" : ""}">
            <td><div class="member-cell" title="${escapeHtml(member.notes || "")}"><span class="avatar">${escapeHtml(initials(member.name))}</span><div><strong>${escapeHtml(member.name)}</strong><small>${escapeHtml(member.email)}</small></div></div></td>
            <td>${row.meetings_total}</td>
            <td>${row.attended_count}</td>
            <td>${row.giveaways_won}</td>
            <td>${row.last_attended_date ? escapeHtml(formatDate(row.last_attended_date)) : '<span class="muted-dash">—</span>'}</td>
            <td>${row.last_contacted_at ? escapeHtml(formatDate(row.last_contacted_at.slice(0, 10))) : '<span class="muted-dash">—</span>'}</td>
            <td class="notes-cell">${escapeHtml(member.notes || "")}</td>
          </tr>`;
        })
        .join("")
    : '<tr><td colspan="7" class="empty-cell">No members yet.</td></tr>';
};

const setView = async (view) => {
  state.view = view;
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
    meetings: "Meetings",
    meeting: currentMeeting()?.book.title || "Meeting",
    books: "Books",
    members: "Members",
    participation: "Participation",
    messages: "Messages & labels",
    templates: "Templates",
  };
  $("#breadcrumb-page").textContent = labels[view];
  if (view === "meetings") renderMeetings();
  if (view === "books") renderBooks();
  if (view === "participation") await loadParticipation();
  if (view === "messages") {
    const meeting = currentMeeting();
    $("#message-meeting-context").textContent = meeting
      ? `Preparing messages for ${meeting.book.title} on ${formatDate(meeting.meeting_date)}.`
      : "Add and open a meeting before preparing messages or labels.";
  }
  if (view === "templates" && !state.templates.length) await loadTemplates();
};

$("#roster-table").addEventListener("change", async (event) => {
  const field = event.target.dataset.rosterField;
  if (!field) return;
  const row = event.target.closest("tr");
  const memberId = Number(row.dataset.memberId);
  try {
    await saveParticipation(memberId, { [field]: event.target.checked });
    showToast("Roster updated.");
  } catch (error) {
    showToast(error.message);
    await loadSelectedMeeting();
  }
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
    ? `<button class="member-search-result member-search-add-new" type="button" data-add-new-member="${escapeHtml(trimmed)}">＋ Add "${escapeHtml(trimmed)}" as a new member</button>`
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

const updateTransitPrintButton = () => {
  $("#print-transit-label").disabled = !(
    state.transitSelectedMemberId && $("#transit-destination").value.trim()
  );
};

$("#transit-member-search").addEventListener("input", (event) => {
  state.transitSelectedMemberId = null;
  updateTransitPrintButton();
  renderMemberSearchResults($("#transit-member-results"), event.target.value, {});
});

$("#transit-member-results").addEventListener("click", (event) => {
  const resultButton = event.target.closest("[data-member-result]");
  if (!resultButton) return;
  const memberId = Number(resultButton.dataset.memberResult);
  const member = state.members.find((entry) => entry.id === memberId);
  if (!member) return;
  state.transitSelectedMemberId = member.id;
  $("#transit-member-search").value = member.name;
  $("#transit-destination").value = member.destination_branch || "";
  $("#transit-member-results").hidden = true;
  updateTransitPrintButton();
});

$("#transit-destination").addEventListener("input", updateTransitPrintButton);

$("#print-transit-label").addEventListener("click", async () => {
  const destination = $("#transit-destination").value.trim();
  if (!state.transitSelectedMemberId || !destination) return;
  await printTransitLabel(state.transitSelectedMemberId, destination);
});

$("#member-form").elements.is_new_registrant.addEventListener("change", updateMemberDeliveryFieldVisibility);
$("#member-form").elements.delivery_method.addEventListener("change", updateMemberDeliveryFieldVisibility);

$("#member-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const id = form.elements.id.value;
  const isNewRegistrant = form.elements.is_new_registrant.checked;
  const deliveryMethod = isNewRegistrant ? form.elements.delivery_method.value : "none";
  const destinationBranch = form.elements.destination_branch.value.trim();
  if (isNewRegistrant && deliveryMethod === "transfer" && !destinationBranch) {
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

$("#meeting-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const id = form.elements.id.value;
  const data = {
    book_id: Number(form.elements.book_id.value),
    meeting_date: form.elements.meeting_date.value,
    meeting_time: form.elements.meeting_time.value.trim() || null,
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
        description: form.elements.description.value.trim() || null,
        organizer_name: form.elements.organizer_name.value.trim() || null,
        organizer_branch: form.elements.organizer_branch.value.trim() || null,
        video_call_url: form.elements.video_call_url.value.trim() || null,
        public: form.elements.public.value === "true",
      }),
    });
    applyClub(updated);
    $("#club-settings-dialog").close();
    showToast("Club settings saved.");
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

$("#question-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const id = form.elements.id.value;
  try {
    await request(
      id
        ? `/bookclub/questions/${id}`
        : `/bookclub/meetings/${state.meetingId}/questions`,
      {
        method: id ? "PATCH" : "POST",
        body: JSON.stringify({ text: form.elements.text.value.trim() }),
      },
    );
    $("#question-dialog").close();
    state.questions = await request(
      `/bookclub/meetings/${state.meetingId}/questions`,
    );
    renderQuestions();
  } catch (error) {
    $("#question-error").textContent = error.message;
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
  if (jumpBadge) return jumpToPendingMeeting(Number(jumpBadge.dataset.jumpToPending));

  const editQuestion = event.target.closest("[data-edit-question]");
  if (editQuestion) {
    const question = state.questions.find(
      (entry) => entry.id === Number(editQuestion.dataset.editQuestion),
    );
    const form = $("#question-form");
    form.elements.id.value = question.id;
    form.elements.text.value = question.text;
    $("#question-dialog-title").textContent = "Edit question";
    return $("#question-dialog").showModal();
  }
  const deleteQuestion = event.target.closest("[data-delete-question]");
  if (deleteQuestion) {
    if (!window.confirm("Delete this discussion question?")) return;
    await request(`/bookclub/questions/${deleteQuestion.dataset.deleteQuestion}`, {
      method: "DELETE",
    });
    state.questions = await request(`/bookclub/meetings/${state.meetingId}/questions`);
    return renderQuestions();
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

  const sortHeaderButton = event.target.closest("[data-sort]");
  if (sortHeaderButton) {
    const key = sortHeaderButton.dataset.sort;
    if (state.participationSort.key === key) state.participationSort.dir *= -1;
    else state.participationSort = { key, dir: 1 };
    return renderParticipation();
  }

  const removeFromRosterButton = event.target.closest("[data-remove-from-roster]");
  if (removeFromRosterButton) {
    const memberId = Number(removeFromRosterButton.dataset.removeFromRoster);
    const entry = state.roster.find((item) => item.member_id === memberId);
    if (!window.confirm(`Remove ${entry?.member?.name || "this member"} from this meeting's roster?`)) return;
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
      renderWelcomeEmails();
      renderMembers();
      return showToast(
        result.sent ? "Email sent." : "Email delivery isn't configured — use Copy instead.",
      );
    } catch (error) {
      return showToast(error.message);
    }
  }
});

$("#roster-search").addEventListener("input", (event) => {
  state.rosterQuery = event.target.value;
  renderRoster();
});
$("#member-search").addEventListener("input", (event) => {
  state.memberQuery = event.target.value;
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
$("#add-member").addEventListener("click", () => openMemberDialog());
$("#edit-club-settings").addEventListener("click", openClubSettingsDialog);
$("#add-book").addEventListener("click", () => openBookDialog());
$("#book-list").addEventListener("click", (event) => {
  if (event.target.closest("#empty-add-book")) openBookDialog();
});
$("#edit-meeting").addEventListener("click", () => openMeetingDialog(currentMeeting()));
$("#delete-meeting").addEventListener("click", async () => {
  const meeting = currentMeeting();
  if (!meeting) return;
  if (
    !window.confirm(
      `Delete the ${formatDate(meeting.meeting_date)} meeting for ${meeting.book.title}? Attendance, the giveaway winner, and questions for this meeting will also be deleted.`,
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
    state.questions = [];
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
$("#add-question").addEventListener("click", () => {
  if (!state.meetingId) return showToast("Add a meeting first.");
  const form = $("#question-form");
  form.reset();
  form.elements.id.value = "";
  $("#question-dialog-title").textContent = "Add question";
  $("#question-dialog").showModal();
});
$("#copy-reminder-list").addEventListener("click", async () => {
  const emails = state.roster.map((entry) => entry.member.email);
  if (!emails.length) return showToast("No one is on this meeting's roster yet.");
  await navigator.clipboard.writeText(emails.join("; "));
  showToast("Address list copied.");
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
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") accountMenu.open = false;
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
