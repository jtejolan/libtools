const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];

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

const formatDate = (value) =>
  new Intl.DateTimeFormat(undefined, { weekday: "short", month: "short", day: "numeric", year: "numeric" }).format(
    new Date(`${value}T12:00:00`),
  );

const API = "/bookclub/community";
const state = { books: [], meetings: [], templates: [] };

// ---- tabs ----
$$(".manage-tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    $$(".manage-tab").forEach((t) => t.classList.toggle("active", t === tab));
    ["books", "meetings", "voting", "date-poll", "templates"].forEach((view) => {
      $(`#${view}-view`).hidden = view !== tab.dataset.view;
    });
  });
});

// ---- dialogs ----
$$("[data-close-dialog]").forEach((button) => {
  button.addEventListener("click", () => $(`#${button.dataset.closeDialog}`).close());
});

// ---- books ----
const renderBooks = () => {
  const list = $("#books-list");
  if (!state.books.length) {
    list.innerHTML = '<p class="muted">No books yet.</p>';
    return;
  }
  list.innerHTML = state.books
    .map(
      (book) => `<article class="user-card" data-book-id="${book.id}">
        <div>
          <h3>${escapeHtml(book.title)}</h3>
          <p class="user-meta">${escapeHtml(book.author)}${book.is_past_selection ? " · Already read" : ""}</p>
        </div>
        <div class="user-actions"><button class="quiet-button" data-edit-book="${book.id}">Edit</button></div>
      </article>`,
    )
    .join("");
};

const loadBooks = async () => {
  state.books = await request(`${API}/books?limit=500`);
  renderBooks();
  const select = $("#meeting-book-select");
  select.innerHTML = state.books.map((book) => `<option value="${book.id}">${escapeHtml(book.title)}</option>`).join("");
};

const openBookDialog = (book = null) => {
  const form = $("#book-form");
  form.reset();
  $("#book-error").textContent = "";
  $("#import-book-status").textContent = "";
  $("#book-dialog-title").textContent = book ? "Edit book" : "Add a book";
  $("#delete-book").hidden = !book;
  form.elements.id.value = book?.id || "";
  if (book) {
    for (const [key, value] of Object.entries(book)) {
      if (key === "is_past_selection") form.elements[key].checked = value;
      else if (form.elements[key] && value != null) form.elements[key].value = value;
    }
  }
  $("#book-dialog").showModal();
};

$("#add-book").addEventListener("click", () => openBookDialog());

$("#books-list").addEventListener("click", (event) => {
  const id = event.target.closest("[data-edit-book]")?.dataset.editBook;
  if (!id) return;
  openBookDialog(state.books.find((book) => String(book.id) === id));
});

$("#import-book").addEventListener("click", async () => {
  const form = $("#book-form");
  const url = form.elements.catalogue_url.value.trim();
  if (!url) {
    $("#import-book-status").textContent = "Paste a catalogue link first.";
    return;
  }
  $("#import-book-status").textContent = "Fetching…";
  try {
    const result = await request(`${API}/books/import`, {
      method: "POST",
      body: JSON.stringify({ catalogue_url: url }),
    });
    for (const [key, value] of Object.entries(result)) {
      if (form.elements[key] && value != null) form.elements[key].value = value;
    }
    $("#import-book-status").textContent = "Details filled in — review before saving.";
  } catch (error) {
    $("#import-book-status").textContent = error.message;
  }
});

$("#book-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  $("#book-error").textContent = "";
  const data = Object.fromEntries(new FormData(form));
  const id = data.id;
  delete data.id;
  data.is_past_selection = form.elements.is_past_selection.checked;
  // Optional fields (isbn especially — min_length=10 in BookCreate/Update)
  // must be omitted rather than sent as "", or Pydantic rejects them.
  for (const key of Object.keys(data)) {
    if (data[key] === "") delete data[key];
  }
  try {
    if (id) await request(`${API}/books/${id}`, { method: "PATCH", body: JSON.stringify(data) });
    else await request(`${API}/books`, { method: "POST", body: JSON.stringify(data) });
    $("#book-dialog").close();
    await loadBooks();
    toast("Book saved.");
  } catch (error) {
    $("#book-error").textContent = error.message;
  }
});

$("#delete-book").addEventListener("click", async () => {
  const id = $("#book-form").elements.id.value;
  if (!id || !confirm("Delete this book?")) return;
  try {
    await request(`${API}/books/${id}`, { method: "DELETE" });
    $("#book-dialog").close();
    await loadBooks();
    toast("Book deleted.");
  } catch (error) {
    $("#book-error").textContent = error.message;
  }
});

// ---- meetings ----
const renderMeetings = () => {
  const list = $("#meetings-list");
  if (!state.meetings.length) {
    list.innerHTML = '<p class="muted">No meetings scheduled yet.</p>';
    return;
  }
  list.innerHTML = state.meetings
    .map(
      (meeting) => `<article class="user-card" data-meeting-id="${meeting.id}">
        <div>
          <h3>${escapeHtml(meeting.book.title)}</h3>
          <p class="user-meta">${escapeHtml(formatDate(meeting.meeting_date))}${meeting.meeting_time ? ` · ${escapeHtml(meeting.meeting_time)}` : ""}${meeting.location ? ` · ${escapeHtml(meeting.location)}` : ""} · <span class="status">${meeting.status}</span></p>
        </div>
        <div class="user-actions"><button class="quiet-button" data-edit-meeting="${meeting.id}">Edit</button></div>
      </article>`,
    )
    .join("");
};

const loadMeetings = async () => {
  state.meetings = await request(`${API}/meetings?limit=500`);
  renderMeetings();
};

const openMeetingDialog = (meeting = null) => {
  if (!state.books.length) {
    toast("Add a book before scheduling a meeting.");
    return;
  }
  const form = $("#meeting-form");
  form.reset();
  $("#meeting-error").textContent = "";
  $("#meeting-dialog-title").textContent = meeting ? "Edit meeting" : "Schedule a meeting";
  $("#delete-meeting").hidden = !meeting;
  form.elements.id.value = meeting?.id || "";
  form.elements.meeting_duration_minutes.value = meeting?.meeting_duration_minutes ?? 90;
  if (meeting) {
    form.elements.book_id.value = meeting.book_id;
    form.elements.meeting_date.value = meeting.meeting_date;
    form.elements.meeting_time.value = meeting.meeting_time || "";
    form.elements.location.value = meeting.location || "";
    form.elements.notes.value = meeting.notes || "";
  }
  $("#meeting-dialog").showModal();
};

$("#add-meeting").addEventListener("click", () => openMeetingDialog());

$("#meetings-list").addEventListener("click", (event) => {
  const id = event.target.closest("[data-edit-meeting]")?.dataset.editMeeting;
  if (!id) return;
  openMeetingDialog(state.meetings.find((meeting) => String(meeting.id) === id));
});

$("#meeting-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  $("#meeting-error").textContent = "";
  const data = Object.fromEntries(new FormData(form));
  const id = data.id;
  delete data.id;
  data.book_id = Number(data.book_id);
  data.meeting_duration_minutes = Number(data.meeting_duration_minutes);
  for (const key of Object.keys(data)) {
    if (data[key] === "") delete data[key];
  }
  try {
    if (id) await request(`${API}/meetings/${id}`, { method: "PATCH", body: JSON.stringify(data) });
    else await request(`${API}/meetings`, { method: "POST", body: JSON.stringify(data) });
    $("#meeting-dialog").close();
    await loadMeetings();
    toast("Meeting saved.");
  } catch (error) {
    $("#meeting-error").textContent = error.message;
  }
});

$("#delete-meeting").addEventListener("click", async () => {
  const id = $("#meeting-form").elements.id.value;
  if (!id || !confirm("Delete this meeting?")) return;
  try {
    await request(`${API}/meetings/${id}`, { method: "DELETE" });
    $("#meeting-dialog").close();
    await loadMeetings();
    toast("Meeting deleted.");
  } catch (error) {
    $("#meeting-error").textContent = error.message;
  }
});

// ---- templates ----
const renderTemplates = () => {
  const list = $("#templates-list");
  if (!state.templates.length) {
    list.innerHTML = '<p class="muted">No templates yet.</p>';
    return;
  }
  list.innerHTML = state.templates
    .map(
      (template) => `<article class="user-card" data-template-key="${escapeHtml(template.key)}">
        <div>
          <h3>${escapeHtml(template.name)}</h3>
          <p class="user-meta">${escapeHtml(template.kind)} · ${escapeHtml(template.key)}</p>
        </div>
        <div class="user-actions">
          ${template.kind === "email" ? `<button class="secondary-button" data-send-template="${escapeHtml(template.key)}">Send to participants</button>` : ""}
          <button class="quiet-button" data-edit-template="${escapeHtml(template.key)}">Edit</button>
        </div>
      </article>`,
    )
    .join("");
};

const loadTemplates = async () => {
  state.templates = await request(`${API}/templates`);
  renderTemplates();
};

const openTemplateDialog = (template = null) => {
  const form = $("#template-form");
  form.reset();
  $("#template-error").textContent = "";
  $("#template-dialog-title").textContent = template ? "Edit template" : "Add a template";
  form.elements.key.disabled = Boolean(template);
  if (template) {
    form.elements.key.value = template.key;
    form.elements.name.value = template.name;
    form.elements.kind.value = template.kind;
    form.elements.subject.value = template.subject || "";
    form.elements.body.value = template.body;
  }
  $("#template-dialog").showModal();
};

$("#add-template").addEventListener("click", () => openTemplateDialog());

$("#templates-list").addEventListener("click", (event) => {
  const key = event.target.closest("[data-edit-template]")?.dataset.editTemplate;
  if (!key) return;
  openTemplateDialog(state.templates.find((template) => template.key === key));
});

$("#templates-list").addEventListener("click", async (event) => {
  const button = event.target.closest("[data-send-template]");
  if (!button) return;
  const key = button.dataset.sendTemplate;
  if (!confirm("Send this email to all subscribed participants now?")) return;
  button.disabled = true;
  try {
    const result = await request(`${API}/broadcast`, {
      method: "POST",
      body: JSON.stringify({ template_key: key }),
    });
    if (!result.delivery_configured) {
      toast(`Email delivery isn't connected yet — would have reached ${result.recipient_count} participant${result.recipient_count === 1 ? "" : "s"}.`);
    } else {
      toast(`Sent to ${result.sent_count} of ${result.recipient_count} participant${result.recipient_count === 1 ? "" : "s"}.`);
    }
    if (result.missing_variables.length) {
      toast(`Note: template had unfilled placeholders: ${result.missing_variables.join(", ")}`);
    }
  } catch (error) {
    toast(error.message);
  } finally {
    button.disabled = false;
  }
});

$("#template-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  $("#template-error").textContent = "";
  const editingKey = form.elements.key.disabled ? form.elements.key.value : null;
  const data = Object.fromEntries(new FormData(form));
  if (editingKey) delete data.key;
  try {
    if (editingKey) await request(`${API}/templates/${editingKey}`, { method: "PATCH", body: JSON.stringify(data) });
    else await request(`${API}/templates`, { method: "POST", body: JSON.stringify(data) });
    $("#template-dialog").close();
    await loadTemplates();
    toast("Template saved.");
  } catch (error) {
    $("#template-error").textContent = error.message;
  }
});

// ---- voting ----
const renderVotingCandidate = (candidate) => {
  const actions =
    candidate.status === "pending"
      ? `<button class="secondary-button" data-approve-candidate="${candidate.id}">Approve</button>
         <button class="quiet-button" data-reject-candidate="${candidate.id}">Reject</button>`
      : "";
  return `<article class="user-card" data-candidate-id="${candidate.id}">
    <div>
      <h3>${escapeHtml(candidate.book.title)}</h3>
      <p class="user-meta">${escapeHtml(candidate.book.author)} · <span class="status${candidate.status === "rejected" ? " disabled" : ""}">${candidate.status}</span>${candidate.vote_count != null ? ` · ${candidate.vote_count} vote${candidate.vote_count === 1 ? "" : "s"}` : ""}${candidate.proposed_by_name ? ` · proposed by ${escapeHtml(candidate.proposed_by_name)}` : ""}</p>
    </div>
    <div class="user-actions">${actions}</div>
  </article>`;
};

const renderVoting = (round) => {
  const toolbarCopy = $("#voting-toolbar-copy");
  const startButton = $("#start-voting-round");
  const closeButton = $("#close-voting-round");
  const addCandidateRow = $("#add-candidate-row");
  const list = $("#voting-list");

  if (!round) {
    toolbarCopy.textContent = "No poll running right now.";
    startButton.hidden = false;
    closeButton.hidden = true;
    addCandidateRow.hidden = true;
    list.innerHTML = "";
    return;
  }

  const open = round.status === "open";
  toolbarCopy.textContent = open ? "Voting is open." : "This poll is closed.";
  startButton.hidden = open;
  closeButton.hidden = !open;
  addCandidateRow.hidden = !open;

  if (open) {
    const candidateBookIds = new Set(round.candidates.map((c) => c.book.id));
    const remaining = state.books.filter((book) => !candidateBookIds.has(book.id));
    $("#candidate-book-select").innerHTML = remaining
      .map((book) => `<option value="${book.id}">${escapeHtml(book.title)}</option>`)
      .join("");
    addCandidateRow.hidden = !remaining.length;
  }

  const winnerNote =
    !open && round.winning_book
      ? `<p class="muted" style="margin-bottom:14px">Winner: <strong>${escapeHtml(round.winning_book.title)}</strong></p>`
      : "";
  list.innerHTML = winnerNote + round.candidates.map(renderVotingCandidate).join("");
};

const loadVoting = async () => {
  try {
    const round = await request(`${API}/voting-round`);
    renderVoting(round);
  } catch (error) {
    if (error.status === 404) renderVoting(null);
    else toast(error.message);
  }
};

$("#start-voting-round").addEventListener("click", () => {
  $("#start-voting-error").textContent = "";
  $("#start-voting-choices").innerHTML = state.books.length
    ? state.books
        .map(
          (book) =>
            `<label><input type="checkbox" name="candidate_book_ids" value="${book.id}" /> ${escapeHtml(book.title)}</label>`,
        )
        .join("")
    : '<p class="muted">Add a book first.</p>';
  $("#start-voting-dialog").showModal();
});

$("#start-voting-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const ids = $$("#start-voting-choices input:checked").map((input) => Number(input.value));
  try {
    const round = await request(`${API}/voting-round`, {
      method: "POST",
      body: JSON.stringify({ candidate_book_ids: ids }),
    });
    $("#start-voting-dialog").close();
    renderVoting(round);
    toast("Voting opened.");
  } catch (error) {
    $("#start-voting-error").textContent = error.message;
  }
});

$("#add-candidate-button").addEventListener("click", async () => {
  const select = $("#candidate-book-select");
  if (!select.value) return;
  try {
    await request(`${API}/voting-round/candidates`, {
      method: "POST",
      body: JSON.stringify({ book_id: Number(select.value) }),
    });
    await loadVoting();
    toast("Candidate added.");
  } catch (error) {
    toast(error.message);
  }
});

$("#voting-list").addEventListener("click", async (event) => {
  const approve = event.target.closest("[data-approve-candidate]");
  const reject = event.target.closest("[data-reject-candidate]");
  if (!approve && !reject) return;
  const id = (approve ?? reject).dataset[approve ? "approveCandidate" : "rejectCandidate"];
  try {
    const round = await request(`${API}/candidates/${id}/${approve ? "approve" : "reject"}`, {
      method: "POST",
    });
    renderVoting(round);
  } catch (error) {
    toast(error.message);
  }
});

$("#close-voting-round").addEventListener("click", async () => {
  if (!confirm("Close voting and pick a winner?")) return;
  try {
    const round = await request(`${API}/voting-round/close`, { method: "POST" });
    renderVoting(round);
    toast("Voting closed.");
  } catch (error) {
    toast(error.message);
  }
});

// ---- date poll ----
const renderDatePollOption = (option) => `<article class="user-card" data-option-id="${option.id}">
    <div>
      <h3>${escapeHtml(formatDate(option.option_date))}</h3>
      <p class="user-meta">${option.vote_count != null ? `${option.vote_count} vote${option.vote_count === 1 ? "" : "s"}` : ""}</p>
    </div>
  </article>`;

const renderDatePoll = (poll) => {
  const toolbarCopy = $("#date-poll-toolbar-copy");
  const startButton = $("#start-date-poll");
  const closeButton = $("#close-date-poll");
  const addRow = $("#add-date-option-row");
  const list = $("#date-poll-list");

  if (!poll) {
    toolbarCopy.textContent = "No date poll running right now.";
    startButton.hidden = false;
    closeButton.hidden = true;
    addRow.hidden = true;
    list.innerHTML = "";
    return;
  }

  const open = poll.status === "open";
  toolbarCopy.textContent = open ? "Voting is open." : "This poll is closed.";
  startButton.hidden = open;
  closeButton.hidden = !open;
  addRow.hidden = !open;

  const winnerNote =
    !open && poll.winning_date
      ? `<p class="muted" style="margin-bottom:14px">Winner: <strong>${escapeHtml(formatDate(poll.winning_date))}</strong></p>`
      : "";
  list.innerHTML = winnerNote + poll.options.map(renderDatePollOption).join("");
};

const loadDatePoll = async () => {
  try {
    const poll = await request(`${API}/date-poll`);
    renderDatePoll(poll);
  } catch (error) {
    if (error.status === 404) renderDatePoll(null);
    else toast(error.message);
  }
};

$("#start-date-poll").addEventListener("click", () => {
  $("#start-date-poll-error").textContent = "";
  $("#start-date-poll-form").reset();
  $("#start-date-poll-dialog").showModal();
});

$("#start-date-poll-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const dates = $$("#start-date-poll-form input[name=option_dates]")
    .map((input) => input.value)
    .filter(Boolean);
  try {
    const poll = await request(`${API}/date-poll`, {
      method: "POST",
      body: JSON.stringify({ option_dates: dates }),
    });
    $("#start-date-poll-dialog").close();
    renderDatePoll(poll);
    toast("Date poll opened.");
  } catch (error) {
    $("#start-date-poll-error").textContent = error.message;
  }
});

$("#add-date-option-button").addEventListener("click", async () => {
  const input = $("#date-option-input");
  if (!input.value) return;
  try {
    const poll = await request(`${API}/date-poll/options`, {
      method: "POST",
      body: JSON.stringify({ option_date: input.value }),
    });
    input.value = "";
    renderDatePoll(poll);
    toast("Date added.");
  } catch (error) {
    toast(error.message);
  }
});

$("#close-date-poll").addEventListener("click", async () => {
  if (!confirm("Close the date poll and pick a winner?")) return;
  try {
    const poll = await request(`${API}/date-poll/close`, { method: "POST" });
    renderDatePoll(poll);
    toast("Date poll closed.");
  } catch (error) {
    toast(error.message);
  }
});

// ---- init ----
$("#logout").addEventListener("click", async () => {
  await request("/auth/logout", { method: "POST" });
  location.href = "/login";
});

(async () => {
  try {
    await request("/auth/me");
    const club = await request("/bookclub/clubs/selected");
    $("#club-eyebrow").textContent = club.name;
    document.title = `${club.name} — Community`;
    await loadBooks();
    await Promise.all([loadMeetings(), loadTemplates(), loadVoting(), loadDatePoll()]);
  } catch {
    location.href = "/bookclub";
  }
})();
