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
  rosterQuery: "",
  memberQuery: "",
  meetingQuery: "",
  bookQuery: "",
};

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const loginDialog = $("#login-dialog");
const clubDialog = $("#club-dialog");
const toast = $("#toast");
const accountMenu = $("#account-menu");

const escapeHtml = (value = "") =>
  String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");

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
  $("#account-menu-name").textContent = user.username;
};

const applyClub = (club) => {
  state.club = club;
  $("#sidebar-club-name").textContent = club.name;
  $("#switch-club").textContent = club.name;
  const publicLink = $("#public-club-link");
  publicLink.hidden = !club.public;
  publicLink.href = `/clubs/${encodeURIComponent(club.slug)}`;
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

const chooseClub = async (clubId) => {
  const club = await request(`/bookclub/clubs/${clubId}/select`, { method: "POST" });
  applyClub(club);
  clubDialog.close();
  await loadCoreData();
  await setView("meetings");
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

const renderBooks = () => {
  const query = state.bookQuery.trim().toLowerCase();
  const books = state.books.filter((book) =>
    [book.title, book.author, book.isbn, book.genres]
      .filter(Boolean)
      .join(" ")
      .toLowerCase()
      .includes(query),
  );
  $("#book-count").textContent = `${state.books.length} ${state.books.length === 1 ? "book" : "books"}`;
  const list = $("#book-list");
  if (!books.length) {
    list.innerHTML = `<div class="empty-collection"><span>▥</span><h2>${query ? "No matching books" : "Your book list is empty"}</h2><p>${query ? "Try a different title, author, ISBN, or genre." : "Add the first title selected for the club."}</p>${query ? "" : '<button class="primary-button" id="empty-add-book" type="button">＋ Add book</button>'}</div>`;
    return;
  }
  list.innerHTML = books
    .map((book) => {
      const cover = safeImageUrl(book.cover_image_url);
      const publicationYear = book.publication_date?.slice(0, 4);
      return `<article class="book-card"><div class="book-cover">${cover ? `<img src="${escapeHtml(cover)}" alt="Cover of ${escapeHtml(book.title)}" loading="lazy" />` : escapeHtml(initials(book.title))}</div><div class="book-card-copy"><h2>${escapeHtml(book.title)}</h2><p class="book-author">${escapeHtml(book.author)}</p><p class="book-description">${escapeHtml(book.description || "No description has been added yet.")}</p><div class="book-meta">${publicationYear ? `<span>${escapeHtml(publicationYear)}</span>` : ""}${book.page_count ? `<span>${book.page_count} pages</span>` : ""}${book.genres ? `<span>${escapeHtml(book.genres)}</span>` : ""}</div></div><div class="book-card-actions"><button type="button" data-edit-book="${book.id}">Edit</button><button class="danger-text" type="button" data-delete-book="${book.id}">Delete</button></div></article>`;
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
      "Set the next book and date, then the active member list will be ready to track.";
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
  $("#checkout-stat").textContent = state.roster.filter(
    (entry) => entry.book_checked_out,
  ).length;
  $("#attendance-stat").textContent = state.roster.filter(
    (entry) => entry.attended,
  ).length;
  $("#transfer-stat").textContent = state.roster.filter(
    (entry) => entry.delivery_method === "transfer",
  ).length;
  renderRoster();
  renderGiveaway();
  renderQuestions();
};

const renderRoster = () => {
  const body = $("#roster-table");
  if (!state.meetingId) {
    body.innerHTML = '<tr><td colspan="5" class="empty-cell">Add a meeting to create its monthly checklist.</td></tr>';
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
    body.innerHTML = `<tr><td colspan="5" class="empty-cell">${query ? "No matching members." : "No members are on this meeting roster yet."}</td></tr>`;
    return;
  }
  body.innerHTML = entries
    .map((entry) => {
      const member = entry.member;
      return `<tr data-member-id="${member.id}">
        <td><div class="member-cell"><span class="avatar">${escapeHtml(initials(member.name))}</span><div><strong>${escapeHtml(member.name)}</strong><small>${escapeHtml(member.email)}</small></div></div></td>
        <td><select class="table-select" data-roster-field="delivery_method" aria-label="Book request for ${escapeHtml(member.name)}">
          <option value="none" ${entry.delivery_method === "none" ? "selected" : ""}>No copy</option>
          <option value="pickup" ${entry.delivery_method === "pickup" ? "selected" : ""}>Pickup at PBRL</option>
          <option value="transfer" ${entry.delivery_method === "transfer" ? "selected" : ""}>Send to branch</option>
        </select></td>
        <td>${
          entry.delivery_method === "transfer"
            ? `<input class="branch-input" data-roster-field="destination_branch" value="${escapeHtml(entry.destination_branch || "")}" placeholder="Branch name" aria-label="Destination branch for ${escapeHtml(member.name)}" />`
            : '<span class="muted-dash">—</span>'
        }</td>
        <td><label class="check-wrap"><input type="checkbox" data-roster-field="book_checked_out" ${entry.book_checked_out ? "checked" : ""} /><span>${entry.book_checked_out ? "Yes" : "No"}</span></label></td>
        <td><label class="check-wrap"><input type="checkbox" data-roster-field="attended" ${entry.attended ? "checked" : ""} /><span>${entry.attended ? "Yes" : "No"}</span></label></td>
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

const renderMembers = () => {
  const query = state.memberQuery.trim().toLowerCase();
  const members = state.members.filter((member) =>
    [member.name, member.email].join(" ").toLowerCase().includes(query),
  );
  $("#member-count").textContent = `${state.members.filter((member) => member.active).length} active · ${state.members.length} total`;
  $("#members-table").innerHTML = members.length
    ? members
        .map(
          (member) => `<tr><td><div class="member-cell"><span class="avatar">${escapeHtml(initials(member.name))}</span><div><strong>${escapeHtml(member.name)}</strong><small>${escapeHtml(member.email)}</small></div></div></td><td>${escapeHtml(formatDate(member.joined_on))}</td><td><span class="status-pill ${member.active ? "" : "inactive"}">${member.active ? "Active" : "Inactive"}</span></td><td><button class="row-action" type="button" data-member-history="${member.id}">View history</button></td><td><button class="row-action" type="button" data-edit-member="${member.id}">Edit</button></td></tr>`,
        )
        .join("")
    : '<tr><td colspan="5" class="empty-cell">No matching members.</td></tr>';
};

const openMemberDialog = (member = null) => {
  const form = $("#member-form");
  form.reset();
  form.elements.id.value = member?.id || "";
  form.elements.name.value = member?.name || "";
  form.elements.email.value = member?.email || "";
  form.elements.joined_on.value = member?.joined_on || today();
  form.elements.active.value = String(member?.active ?? true);
  form.elements.notes.value = member?.notes || "";
  $("#member-dialog-title").textContent = member ? "Edit member" : "Add member";
  $("#member-error").textContent = "";
  $("#member-dialog").showModal();
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
  $("#history-content").innerHTML = history.length
    ? `<div class="history-list">${history
        .map(
          (entry) => `<article class="history-row"><div><strong>${escapeHtml(entry.meeting.book.title)}</strong><small>${escapeHtml(formatDate(entry.meeting.meeting_date))}</small></div><span class="history-mark ${entry.book_checked_out ? "yes" : "no"}">${entry.book_checked_out ? "Book ✓" : "No book"}</span><span class="history-mark ${entry.attended ? "yes" : "no"}">${entry.attended ? "Attended ✓" : "Absent"}</span></article>`,
        )
        .join("")}</div>`
    : '<div class="empty-card"><p>No meeting history yet.</p></div>';
  $("#history-dialog").showModal();
};

const renderEmailPreviews = (previews) => {
  const container = $("#email-previews");
  if (!previews.length) {
    container.innerHTML = '<div class="empty-card"><span>⌕</span><p>No members match that recipient filter.</p></div>';
    return;
  }
  container.innerHTML = previews
    .map(
      (preview, index) => `<article class="email-card"><header><div><h3>${escapeHtml(preview.member_name)}</h3><small>${escapeHtml(preview.email)}</small></div><button class="copy-button" type="button" data-copy-email="${index}">Copy</button></header><strong>${escapeHtml(preview.subject)}</strong><pre>${escapeHtml(preview.body)}</pre>${preview.missing_variables.length ? `<p class="form-error">Missing: ${escapeHtml(preview.missing_variables.join(", "))}</p>` : ""}</article>`,
    )
    .join("");
  container._previews = previews;
};

const previewEmails = async () => {
  if (!state.meetingId) return showToast("Add a meeting first.");
  const filter = $("#recipient-filter").value;
  try {
    const recipients = await request(
      `/bookclub/meetings/${state.meetingId}/recipients?filter=${encodeURIComponent(filter)}`,
    );
    const previews = await request(
      `/bookclub/meetings/${state.meetingId}/emails/preview`,
      {
        method: "POST",
        body: JSON.stringify({
          email_type: $("#email-type").value,
          member_ids: recipients.map((member) => member.id),
        }),
      },
    );
    const recipientIds = new Set(recipients.map((member) => member.id));
    renderEmailPreviews(
      filter === "all"
        ? previews
        : previews.filter((preview) => recipientIds.has(preview.member_id)),
    );
  } catch (error) {
    showToast(error.message);
  }
};

const printLabels = async () => {
  if (!state.meetingId) return showToast("Add a meeting first.");
  try {
    const labels = await request(
      `/bookclub/meetings/${state.meetingId}/transit-labels/render`,
      { method: "POST", body: "{}" },
    );
    if (!labels.length) return showToast("No branch transfers need labels.");
    $("#print-sheet").innerHTML = labels
      .map((label) => `<article class="print-label">${escapeHtml(label.body)}</article>`)
      .join("");
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
    messages: "Messages & labels",
    templates: "Templates",
  };
  $("#breadcrumb-page").textContent = labels[view];
  if (view === "meetings") renderMeetings();
  if (view === "books") renderBooks();
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
    if (field === "delivery_method") {
      const entry = state.roster.find((item) => item.member_id === memberId);
      if (event.target.value === "transfer") {
        entry.delivery_method = "transfer";
        renderMeetingView();
        document
          .querySelector(`tr[data-member-id="${memberId}"] .branch-input`)
          ?.focus();
        return;
      }
      await saveParticipation(memberId, {
        delivery_method: event.target.value,
      });
    } else if (field === "destination_branch") {
      if (!event.target.value.trim()) return showToast("Enter a destination branch.");
      await saveParticipation(memberId, {
        delivery_method: "transfer",
        destination_branch: event.target.value.trim(),
      });
    } else {
      await saveParticipation(memberId, { [field]: event.target.checked });
    }
    showToast("Monthly checklist updated.");
  } catch (error) {
    showToast(error.message);
    await loadSelectedMeeting();
  }
});

$("#member-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const id = form.elements.id.value;
  const data = {
    name: form.elements.name.value.trim(),
    email: form.elements.email.value.trim(),
    joined_on: form.elements.joined_on.value,
    active: form.elements.active.value === "true",
    notes: form.elements.notes.value.trim() || null,
  };
  try {
    await request(id ? `/bookclub/members/${id}` : "/bookclub/members", {
      method: id ? "PATCH" : "POST",
      body: JSON.stringify(data),
    });
    if (!id && state.meetingId) {
      await request(`/bookclub/meetings/${state.meetingId}/roster/sync`, {
        method: "POST",
      });
    }
    $("#member-dialog").close();
    await loadCoreData();
    showToast(id ? "Member updated." : "Member added to the club.");
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
    showToast(id ? "Meeting updated." : "Meeting added with all active members.");
  } catch (error) {
    $("#meeting-error").textContent = error.message;
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
    if (user.role !== "admin" && !user.tools.includes("bookclub")) {
      $("#login-error").textContent = "Book Club Manager access is required.";
      return;
    }
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
  const copyButton = event.target.closest("[data-copy-email]");
  if (copyButton) {
    const preview = $("#email-previews")._previews[Number(copyButton.dataset.copyEmail)];
    await navigator.clipboard.writeText(
      `To: ${preview.email}\nSubject: ${preview.subject}\n\n${preview.body}`,
    );
    return showToast("Email copied.");
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
$("#add-member").addEventListener("click", () => openMemberDialog());
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
      `Delete the ${formatDate(meeting.meeting_date)} meeting for ${meeting.book.title}? Attendance, checkout records, the giveaway winner, and questions for this meeting will also be deleted.`,
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
$("#sync-roster").addEventListener("click", async () => {
  if (!state.meetingId) return showToast("Add a meeting first.");
  const result = await request(`/bookclub/meetings/${state.meetingId}/roster/sync`, {
    method: "POST",
  });
  await loadSelectedMeeting();
  showToast(result.added ? `${result.added} member${result.added === 1 ? "" : "s"} added.` : "The roster is already current.");
});
$("#add-question").addEventListener("click", () => {
  if (!state.meetingId) return showToast("Add a meeting first.");
  const form = $("#question-form");
  form.reset();
  form.elements.id.value = "";
  $("#question-dialog-title").textContent = "Add question";
  $("#question-dialog").showModal();
});
$("#preview-email").addEventListener("click", previewEmails);
$("#print-labels").addEventListener("click", printLabels);
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
    if (user.role !== "admin" && !user.tools.includes("bookclub")) return showLogin();
    applyUser(user);
    await loadClubs();
  } catch (error) {
    if (error.status !== 401) showToast(error.message);
  }
};

initialize();
