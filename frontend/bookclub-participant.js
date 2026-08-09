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

const participantState = { participantId: null, books: [], upcomingMeeting: null, readingProgress: null };

const formatTimestamp = (value) =>
  new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", year: "numeric" }).format(new Date(value));

const renderAnnouncements = (announcements) => {
  $("#announcements-content").innerHTML = announcements.length
    ? announcements
        .map(
          (item) => `<article class="user-card" style="align-items:start">
            <div>
              ${item.pinned ? '<p class="eyebrow" style="margin-bottom:4px">Pinned</p>' : ""}
              <h3>${escapeHtml(item.title)}</h3>
              <p class="user-meta">${escapeHtml(formatTimestamp(item.published_at))}</p>
              <p style="white-space:pre-wrap;margin:.6rem 0 0">${escapeHtml(item.body)}</p>
            </div>
          </article>`,
        )
        .join("")
    : '<p class="muted">No announcements right now.</p>';
};

const loadAnnouncements = async () => renderAnnouncements(await request("/participant/announcements"));

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
    <div class="calendar-actions"><a class="calendar-link" href="${escapeHtml(data.google_calendar_url)}" target="_blank" rel="noopener">Add to Google Calendar ↗</a><a class="calendar-link" href="${escapeHtml(data.ics_calendar_url)}" download>Download calendar event</a></div>
    <p class="muted" style="margin-top:14px">${data.rsvp_status ? "Your response is saved. You can change it anytime before the meeting." : "Let your facilitator know if you plan to join."}</p>`;
};

const progressLabels = { not_started: "Not started", reading: "Reading", finished: "Finished" };

const renderCurrentReading = (data, progress) => {
  const section = $("#current-reading-section");
  if (!data) { section.hidden = true; return; }
  const book = data.meeting.book;
  section.hidden = false;
  $("#current-reading-title").textContent = book.title;
  $("#current-reading-meta").textContent = `${book.author} · Discussing ${formatDate(data.meeting.meeting_date)}`;
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
  const content = $("#voting-content");
  if (!round) {
    $("#voting-heading").textContent = "Voting";
    content.innerHTML = '<p class="muted">No vote is open right now. Check back soon.</p>';
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
  const content = $("#date-poll-content");
  if (!poll) {
    $("#date-poll-heading").textContent = "Meeting date";
    content.innerHTML = '<p class="muted">No date poll is open right now.</p>';
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

const ratingsState = { participantId: null, pendingStars: {} };

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
  const books = participantState.books;
  if (!books.length) {
    list.innerHTML = '<p class="muted">Your club hasn\'t added any books yet.</p>';
    return;
  }
  const ratingsByBook = await Promise.all(
    books.map((book) => request(`/participant/books/${book.id}/ratings`)),
  );
  list.innerHTML = books.map((book, index) => renderBookRatingCard(book, ratingsByBook[index])).join("");
};

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
    toast("Rating saved.");
    await loadRatings();
    await loadActivity();
  } catch (error) {
    toast(error.message);
  }
});

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
    $("#notification-error").textContent = "";
    $("#notification-dialog").showModal();
  } catch (error) { toast(error.message); }
});
$("#close-notification-dialog").addEventListener("click", () => $("#notification-dialog").close());
$("#notification-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const data = Object.fromEntries(["announcements", "polls", "meeting_reminders", "discussion_replies"].map((name) => [name, form.elements[name].checked]));
  try {
    notificationPreferences = await request("/participant/notification-preferences", { method: "PUT", body: JSON.stringify(data) });
    $("#notification-dialog").close();
    toast("Notification preferences saved.");
  } catch (error) { $("#notification-error").textContent = error.message; }
});

(async () => {
  try {
    const participant = await request("/participant/auth/me");
    render(participant);
    ratingsState.participantId = participant.id;
    participantState.participantId = participant.id;
    participantState.books = await request("/participant/books");
    await Promise.all([loadAnnouncements(), loadRsvp(), loadVoting(), loadDatePoll(), loadRatings(), loadActivity(), loadNotificationPreferences()]);
  } catch {
    location.href = "/";
  }
})();
