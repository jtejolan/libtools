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
};

const formatTimestamp = (value) =>
  new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", year: "numeric" }).format(new Date(value));

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
  const content = $("#rsvp-content");
  if (!data) {
    $("#rsvp-heading").textContent = "No meeting scheduled";
    content.innerHTML = '<p class="muted">Your facilitator hasn’t scheduled the next gathering yet.</p>';
    return;
  }
  const meeting = data.meeting;
  participantState.upcomingMeeting = data;
  $("#rsvp-heading").textContent = meeting.book.title;
  const options = [
    ["attending", "I’m attending"],
    ["maybe", "Maybe"],
    ["not_attending", "Can’t attend"],
  ];
  content.innerHTML = `<p>${escapeHtml(formatDate(meeting.meeting_date))}${meeting.meeting_time ? ` · ${escapeHtml(meeting.meeting_time)}` : ""}${meeting.location ? ` · ${escapeHtml(meeting.location)}` : ""}</p>
    <div class="meeting-actions">
      ${options.map(([status, label]) => `<button class="${data.rsvp_status === status ? "primary-button" : "secondary-button"}" data-rsvp="${status}" data-meeting-id="${meeting.id}">${label}</button>`).join("")}
    </div>
    <div class="calendar-actions">${data.video_call_url ? `<a class="calendar-link" href="${escapeHtml(data.video_call_url)}" target="_blank" rel="noopener">Join online ↗</a>` : ""}<a class="calendar-link" href="${escapeHtml(data.google_calendar_url)}" target="_blank" rel="noopener">Add to Google Calendar ↗</a><a class="calendar-link" href="${escapeHtml(data.ics_calendar_url)}" download>Download calendar event</a></div>
    <p class="muted" style="margin-top:14px">${data.rsvp_status ? "Your response is saved. You can change it anytime before the meeting." : "Please respond before the meeting so your facilitator can plan."}</p>
    ${(meeting.notes || data.discussion_questions?.length) ? `<div class="meeting-details">${meeting.notes ? `<p><strong>Before you come</strong><br>${escapeHtml(meeting.notes)}</p>` : ""}${data.discussion_questions?.length ? `<strong>Discussion starters</strong><ul>${data.discussion_questions.map((question) => `<li>${escapeHtml(question)}</li>`).join("")}</ul>` : ""}</div>` : ""}`;
  renderActionCenter();
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
    .join("") + (progress?.status ? `<button type="button" class="quiet-button" data-reading-status="" data-book-id="${book.id}">Clear</button>` : "");
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

$("#rsvp-content").addEventListener("click", async (event) => {
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
    .join("")}</div>${proposeForm}${pendingCopy}`;
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

const renderBookRatingCard = (book, ratingsData) => {
  const mine = ratingsData.ratings.find((entry) => entry.participant_id === ratingsState.participantId);
  const selectedStars = ratingsState.pendingStars[book.id] ?? mine?.rating ?? 0;
  const stars = [1, 2, 3, 4, 5]
    .map(
      (n) =>
        `<button type="button" class="star-button${n <= selectedStars ? " is-filled" : ""}" data-book-id="${book.id}" data-star="${n}" aria-label="Rate ${n} star${n > 1 ? "s" : ""}">★</button>`,
    )
    .join("");
  const others = ratingsData.ratings.filter((entry) => entry.participant_id !== ratingsState.participantId);
  const averageCopy = ratingsData.count ? `${ratingsData.average}★ average (${ratingsData.count} rating${ratingsData.count > 1 ? "s" : ""})` : "No ratings yet";

  return `<details class="rating-card" data-book-id="${book.id}">
    <summary style="cursor:pointer"><h3 style="display:inline">${escapeHtml(book.title)}</h3><p class="user-meta">${escapeHtml(book.author)} · ${averageCopy}${mine ? ` · You rated ${mine.rating}★` : ""}</p></summary>
    <div style="padding-top:14px">
    <div class="star-row">${stars}</div>
    <textarea class="rating-review" data-book-id="${book.id}" placeholder="Optional review" rows="2">${mine?.review_text ? escapeHtml(mine.review_text) : ""}</textarea>
    <button class="secondary-button" data-save-rating="${book.id}">${mine ? "Update rating" : "Save rating"}</button>
    ${
      others.length
        ? `<details class="rating-others"><summary>${others.length} other review${others.length > 1 ? "s" : ""}</summary>${others
            .map(
              (entry) =>
                `<p><strong>${escapeHtml(entry.participant_name)}</strong> rated ${entry.rating}★${entry.review_text ? `: ${escapeHtml(entry.review_text)}` : ""}</p>`,
            )
            .join("")}</details>`
        : ""
    }
    </div>
  </details>`;
};

const loadRatings = async () => {
  const list = $("#ratings-list");
  const groups = [
    ["Currently reading", participantState.library.current],
    ["Up next", participantState.library.up_next],
    ["Previously read", participantState.library.previously_read],
  ];
  const query = $("#library-search").value.trim().toLocaleLowerCase();
  const books = [...new Map(groups.flatMap(([, items]) => items).map((book) => [book.id, book])).values()];
  if (!books.length) {
    list.innerHTML = '<p class="muted">No books have been scheduled or completed yet.</p>';
    return;
  }
  const missing = books.filter((book) => !ratingsState.dataByBook[book.id]);
  const loaded = await Promise.all(missing.map((book) => request(`/participant/books/${book.id}/ratings`)));
  missing.forEach((book, index) => { ratingsState.dataByBook[book.id] = loaded[index]; });
  ratingsState.mineByBook = Object.fromEntries(books.map((book) => [book.id, ratingsState.dataByBook[book.id].ratings.find((entry) => entry.participant_id === ratingsState.participantId) || null]));
  list.innerHTML = groups.map(([label, items]) => {
    const filtered = items.filter((book) => !query || `${book.title} ${book.author}`.toLocaleLowerCase().includes(query));
    return filtered.length ? `<section class="library-group"><h3>${label}</h3><div class="user-list">${filtered.map((book) => renderBookRatingCard(book, ratingsState.dataByBook[book.id])).join("")}</div></section>` : "";
  }).join("") || '<p class="muted">No books match your search.</p>';
  renderPostMeeting();
  renderActionCenter();
};

$("#library-search").addEventListener("input", () => loadRatings().catch((error) => toast(error.message)));

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
  $("#post-meeting-actions").innerHTML = `${actionButton(mine ? "Update my review" : "Rate this book", "library-section")}<button class="secondary-button" type="button" data-open-discussion-book="${book.id}">Open discussion</button>`;
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
  $("#activity-list").innerHTML = activity.recent.length
    ? activity.recent.map((item) => `<div class="activity-item"><p><strong>${escapeHtml(item.label)}</strong>${item.detail ? ` · ${escapeHtml(item.detail)}` : ""}</p><small>${escapeHtml(formatTimestamp(item.occurred_at))}</small></div>`).join("")
    : '<p class="muted">Your ratings, votes, proposals, and reading updates will appear here.</p>';
};

const loadActivity = async () => renderActivity(await request("/participant/activity"));

const avatarMarkup = (profile) => profile.avatar_url
  ? `<span class="member-avatar"><img src="${escapeHtml(profile.avatar_url)}" alt="" /></span>`
  : `<span class="member-avatar">${escapeHtml(Array.from(profile.name || "?")[0]?.toLocaleUpperCase() || "?")}</span>`;

const renderDirectory = (members) => {
  $("#member-directory").innerHTML = members.length
    ? members.map((member) => `<article class="directory-card"><div class="discussion-author">${avatarMarkup(member)}<div><strong>${escapeHtml(member.name)}${member.is_self ? " (you)" : ""}</strong>${member.bio ? `<p class="muted">${escapeHtml(member.bio)}</p>` : '<p class="muted">No introduction yet.</p>'}</div></div></article>`).join("")
    : '<p class="muted">No members have joined the directory yet.</p>';
};

const loadDirectory = async () => renderDirectory(await request("/participant/members"));

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
    await Promise.all([loadAnnouncements(), loadRsvp(), loadVoting(), loadDatePoll(), loadRatings(), loadActivity(), loadNotificationPreferences(), loadDirectory()]);
    const discussionBook = participantState.library.current[0] || participantState.library.previously_read[0];
    if (discussionBook) await loadDiscussion(discussionBook.id);
    renderPostMeeting();
    renderActionCenter();
  } catch {
    location.href = "/";
  }
})();
