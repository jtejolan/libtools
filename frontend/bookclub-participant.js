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
  $("#manage-panel").hidden = participant.role !== "owner";

  const panel = $("#email-panel");
  if (!participant.email_verified) {
    panel.hidden = false;
    $("#email-copy").textContent = `${participant.email} is waiting to be verified before it can be used for password resets.`;
  } else {
    panel.hidden = true;
  }
};

const participantState = { participantId: null, books: [] };

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

  return `<article class="rating-card" data-book-id="${book.id}">
    <h3>${escapeHtml(book.title)}</h3>
    <p class="user-meta">${escapeHtml(book.author)} · ${averageCopy}</p>
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
  </article>`;
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

(async () => {
  try {
    const participant = await request("/participant/auth/me");
    render(participant);
    ratingsState.participantId = participant.id;
    participantState.participantId = participant.id;
    participantState.books = await request("/participant/books");
    await Promise.all([loadVoting(), loadDatePoll(), loadRatings()]);
  } catch {
    location.href = "/";
  }
})();
