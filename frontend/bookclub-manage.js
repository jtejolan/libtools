const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const API = "/bookclub/community";
const PARTICIPANT_PORTAL_ORIGIN = "https://bookclub.libtools.app";
const state = { books: [], announcements: [], discussions: [], suggestions: [], overview: null, votingRound: null, datePoll: null, club: null };

const request = async (url, options = {}) => {
  const response = await fetch(url, { ...options, cache: "no-store", headers: { ...(options.body ? { "Content-Type": "application/json" } : {}), ...options.headers } });
  if (response.status === 204) return null;
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = body.detail;
    throw Object.assign(new Error(typeof detail === "string" ? detail : detail?.[0]?.msg || "Something went wrong."), { status: response.status });
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

const formatDate = (value) => new Intl.DateTimeFormat(undefined, { weekday: "short", month: "short", day: "numeric", year: "numeric" }).format(new Date(`${value}T12:00:00`));
const formatTimestamp = (value) => new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", year: "numeric" }).format(new Date(value));
const capitalizeFirst = (value = "") => value ? value[0].toLocaleUpperCase() + value.slice(1) : "";

const applyManagerShell = (user, club) => {
  state.club = club;
  $("#sidebar-club-name").textContent = club.name;
  $("#switch-club").textContent = club.name;
  $("#club-eyebrow").textContent = club.name;
  $("#user-badge").textContent = user.role === "admin" ? "Administrator" : "Member";
  $("#account-menu-name").textContent = capitalizeFirst(user.name);
  $("#account-menu-username").textContent = `@${user.username}`;
  $$('[data-platform-admin-only]').forEach((element) => { element.hidden = user.role !== "admin"; });
  const publicLink = $("#public-club-link");
  publicLink.hidden = !club.public;
  publicLink.href = `${PARTICIPANT_PORTAL_ORIGIN}/clubs/${encodeURIComponent(club.slug)}`;
  $("#invite-readers").innerHTML = club.enrollment_policy === "closed"
    ? '<span aria-hidden="true">↗</span> Share public page'
    : '<span aria-hidden="true">＋</span> Invite readers';
};

const selectView = (view) => {
  $$(".manage-tab").forEach((tab) => tab.classList.toggle("active", tab.dataset.view === view));
  ["overview", "voting", "date-poll", "announcements", "discussions"].forEach((name) => { $(`#${name}-view`).hidden = name !== view; });
};

$$(".manage-tab").forEach((tab) => tab.addEventListener("click", () => selectView(tab.dataset.view)));
$$("[data-close-dialog]").forEach((button) => button.addEventListener("click", () => $(`#${button.dataset.closeDialog}`).close()));

const participantInviteUrl = (club) => `${PARTICIPANT_PORTAL_ORIGIN}/clubs/${encodeURIComponent(club.slug)}`;

const copyText = async (value) => {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(value);
    return;
  }
  const temporary = document.createElement("textarea");
  temporary.value = value;
  temporary.setAttribute("readonly", "");
  temporary.style.position = "fixed";
  temporary.style.opacity = "0";
  document.body.append(temporary);
  temporary.select();
  const copied = document.execCommand("copy");
  temporary.remove();
  if (!copied) throw new Error("Copying is unavailable in this browser");
};

const openInviteDialog = () => {
  const club = state.club;
  if (!club) return;
  const publicClub = Boolean(club.public);
  $("#invite-private-state").hidden = publicClub;
  $("#invite-share-content").hidden = !publicClub;
  if (publicClub) {
    const inviteOnly = club.enrollment_policy === "invite_only";
    const closed = club.enrollment_policy === "closed";
    $("#invite-dialog-title").textContent = closed ? "Share the public page" : "Invite readers";
    $("#invite-dialog-intro").textContent = closed
      ? "Readers can view the book and meeting, but new account activation is closed."
      : inviteOnly
        ? "Share the club page with readers whose email is already on your Members roster."
        : "Share one link. Readers can learn about the club, join, or sign in.";
    $("#invite-sharing-tip").innerHTML = inviteOnly
      ? '<span aria-hidden="true">✦</span><strong>Invitation-only club</strong> Add each reader’s email in Members before sending this link.'
      : closed
        ? '<span aria-hidden="true">✦</span><strong>Enrollment closed</strong> Existing linked participants can still sign in from this page.'
        : '<span aria-hidden="true">✦</span><strong>Sharing tip</strong> Add this link to meeting reminders and registration emails so readers can always find their way back.';
    $("#invite-qr-label").textContent = closed ? "Scan to view" : "Scan to join";
    const url = participantInviteUrl(club);
    $("#invite-link-value").value = url;
    $("#invite-code-value").textContent = club.slug;
    $("#invite-preview-link").href = url;
    $("#invite-qr-image").src = `${API}/invite-qr.svg`;
    $("#invite-qr-image").alt = `QR code for the ${club.name} invitation`;
    $("#invite-qr-download").href = `${API}/invite-qr.svg`;
    $("#invite-qr-download").download = `${club.slug}-invite-qr.svg`;
    $("#invite-qr-club-name").textContent = club.name;
  }
  $("#invite-readers-dialog").showModal();
};

$("#invite-readers").addEventListener("click", openInviteDialog);
$("#preview-as-reader").addEventListener("click", async () => {
  try {
    const { url } = await request(`${API}/reader-preview`, { method: "POST" });
    window.open(url, "_blank", "noopener");
  } catch (error) {
    toast(error.message);
  }
});
$$("[data-copy-invite]").forEach((button) => button.addEventListener("click", async () => {
  const value = button.dataset.copyInvite === "code" ? state.club?.slug : participantInviteUrl(state.club);
  try {
    await copyText(value);
    toast(button.dataset.copyInvite === "code" ? "Club code copied." : "Invitation link copied.");
  } catch (error) {
    toast(error.message);
  }
}));

const renderOverview = (overview) => {
  state.overview = overview;
  const meeting = overview.next_meeting;
  const counts = overview.rsvp_counts;
  const responseCount = counts.attending + counts.maybe + counts.not_attending;
  const responseRate = overview.member_count ? Math.round((responseCount / overview.member_count) * 100) : 0;
  const pendingSuggestions = state.suggestions.filter((item) => item.status === "pending").length;
  const votingOpen = state.votingRound?.status === "open";
  const datePollOpen = state.datePoll?.status === "open";
  const latestAnnouncement = state.announcements[0];
  const latestDiscussion = state.discussions[0];
  const bookVoteCount = state.votingRound?.candidates?.reduce((total, item) => total + (item.vote_count || 0), 0) || 0;
  const dateVoteCount = state.datePoll?.options?.reduce((total, item) => total + (item.vote_count || 0), 0) || 0;
  const meetingMarkup = meeting
    ? `<section class="community-meeting-feature"><div class="community-meeting-book">${meeting.book.cover_image_url ? `<img src="${escapeHtml(meeting.book.cover_image_url)}" alt="" />` : '<span aria-hidden="true">◇</span>'}<div><p class="eyebrow"><span></span>Next gathering</p><h2>${escapeHtml(meeting.book.title)}</h2><p class="community-meeting-author">${escapeHtml(meeting.book.author)}</p><div class="community-meeting-meta"><span>${escapeHtml(formatDate(meeting.meeting_date))}</span>${meeting.meeting_time ? `<span>${escapeHtml(meeting.meeting_time)}</span>` : ""}${meeting.location ? `<span>${escapeHtml(meeting.location)}</span>` : ""}</div><a class="secondary-button button-link" href="/bookclub?action=view-meetings">Open session manager</a></div></div><div class="community-response-card"><div class="community-response-heading"><div><span>Reader response</span><strong>${responseCount} of ${overview.member_count}</strong></div><div class="community-response-ring" style="--response:${responseRate}" aria-label="${responseRate}% have responded"><span>${responseRate}%</span></div></div><div class="community-response-track" aria-hidden="true"><span class="is-attending" style="flex:${counts.attending}"></span><span class="is-maybe" style="flex:${counts.maybe}"></span><span class="is-not-attending" style="flex:${counts.not_attending}"></span><span class="is-open" style="flex:${counts.no_response}"></span></div><div class="community-response-breakdown"><span><i class="is-attending"></i><strong>${counts.attending}</strong> attending</span><span><i class="is-maybe"></i><strong>${counts.maybe}</strong> maybe</span><span><i class="is-not-attending"></i><strong>${counts.not_attending}</strong> can’t attend</span><span><i class="is-open"></i><strong>${counts.no_response}</strong> no response</span></div><small>RSVPs are optional and update automatically.</small></div></section>`
    : `<section class="community-meeting-feature is-empty"><div><p class="eyebrow"><span></span>Next gathering</p><h2>Give the community something to gather around</h2><p>Schedule a meeting to bring the book, responses, and session planning together here.</p><a class="primary-button button-link" href="/bookclub?action=view-meetings">Plan a meeting</a></div><span class="community-empty-mark" aria-hidden="true">◇</span></section>`;
  const actions = [
    { tone: overview.pending_book_proposals ? "warm" : "quiet", label: "Reader suggestions", title: overview.pending_book_proposals ? `${overview.pending_book_proposals} title${overview.pending_book_proposals === 1 ? "" : "s"} awaiting review` : "Suggestion queue is clear", copy: pendingSuggestions ? "Readers have shared books for you to consider." : "New participant ideas will collect here.", action: overview.pending_book_proposals ? "Review" : "View", view: "voting" },
    { tone: votingOpen ? "active" : "quiet", label: "Next-book decision", title: votingOpen ? "Book voting is open" : "No book poll is open", copy: votingOpen ? `${state.votingRound.candidates.length} choices · ${bookVoteCount} vote${bookVoteCount === 1 ? "" : "s"} so far` : "Start one when the club is ready to choose.", action: votingOpen ? "See results" : "Set up", view: "voting" },
    { tone: datePollOpen ? "active" : "quiet", label: "Meeting date", title: datePollOpen ? "Date voting is open" : "No date poll is open", copy: datePollOpen ? `${state.datePoll.options.length} options · ${dateVoteCount} selection${dateVoteCount === 1 ? "" : "s"} so far` : "Collect everyone’s availability when needed.", action: datePollOpen ? "See dates" : "Set up", view: "date-poll" },
  ];
  const recentItems = [
    latestAnnouncement ? `<article class="community-recent-item"><span class="community-recent-icon">A</span><div><small>Latest announcement · ${escapeHtml(formatTimestamp(latestAnnouncement.published_at))}</small><strong>${escapeHtml(latestAnnouncement.title)}</strong><p>${escapeHtml(latestAnnouncement.body)}</p></div><button type="button" data-overview-view="announcements">Open</button></article>` : "",
    latestDiscussion ? `<article class="community-recent-item"><span class="community-recent-icon is-discussion">↗</span><div><small>Latest discussion · ${escapeHtml(latestDiscussion.book_title)}</small><strong>${escapeHtml(latestDiscussion.author_name)}</strong><p>${escapeHtml(latestDiscussion.body)}</p></div><button type="button" data-overview-view="discussions">Open</button></article>` : "",
  ].filter(Boolean).join("");
  $("#community-overview-dashboard").innerHTML = `${meetingMarkup}<section class="community-pulse"><header><div><p class="eyebrow"><span></span>Club pulse</p><h2>Between-meeting activity</h2></div><p>A useful snapshot of participation, not account administration.</p></header><div class="community-pulse-grid"><article><span>Readers</span><strong>${overview.verified_account_count}<small> / ${overview.member_count}</small></strong><p>active in the community</p></article><article><span>Conversation</span><strong>${state.discussions.length}</strong><p>posts and replies</p></article><article><span>Updates</span><strong>${state.announcements.length}</strong><p>announcements shared</p></article><article><span>Ideas</span><strong>${pendingSuggestions}</strong><p>reader suggestions to review</p></article></div></section><div class="community-overview-columns"><section class="community-action-centre"><header><p class="eyebrow"><span></span>Facilitator focus</p><h2>Open decisions</h2><p>Move the few things that shape what the club does next.</p></header><div class="community-action-list">${actions.map((item) => `<article class="community-action-row is-${item.tone}"><span class="community-action-dot"></span><div><small>${item.label}</small><strong>${item.title}</strong><p>${item.copy}</p></div><button type="button" data-overview-view="${item.view}">${item.action} <span aria-hidden="true">→</span></button></article>`).join("")}</div></section><section class="community-recent"><header><div><p class="eyebrow"><span></span>Recently</p><h2>From the community</h2></div><button type="button" data-overview-announcement>Share an update</button></header>${recentItems || '<div class="community-recent-empty"><span aria-hidden="true">✦</span><strong>The conversation starts here</strong><p>Share an announcement or invite readers to begin building activity.</p><button class="secondary-button" type="button" data-overview-announcement>New announcement</button></div>'}</section></div>`;
};

const loadOverview = async () => renderOverview(await request(`${API}/overview`));
$("#overview-view").addEventListener("click", (event) => {
  const view = event.target.closest("[data-overview-view]")?.dataset.overviewView;
  if (view) selectView(view);
  if (event.target.closest("[data-overview-announcement]")) openAnnouncement();
});

const renderAnnouncements = () => {
  $("#announcements-list").innerHTML = state.announcements.length ? state.announcements.map((item) => `<article class="user-card announcement-card"><div>${item.pinned ? '<div class="pin-mark">Pinned</div>' : ""}<h3>${escapeHtml(item.title)}</h3><p class="user-meta">Published ${escapeHtml(formatTimestamp(item.published_at))}</p><p class="announcement-body">${escapeHtml(item.body)}</p></div><div class="user-actions"><button class="quiet-button" data-edit-announcement="${item.id}">Edit</button></div></article>`).join("") : '<p class="empty-state">No announcements yet. Publish a welcome message or an update about the next discussion.</p>';
};
const loadAnnouncements = async () => { state.announcements = await request(`${API}/announcements`); renderAnnouncements(); if (state.overview) renderOverview(state.overview); };

const loadDiscussions = async () => {
  state.discussions = await request(`${API}/discussion`);
  $("#discussion-moderation-list").innerHTML = state.discussions.length ? state.discussions.map((post) => `<article class="user-card"><div><p class="eyebrow">${escapeHtml(post.book_title)}${post.parent_id ? " · Reply" : ""}${post.spoiler ? " · Spoiler" : ""}</p><h3>${escapeHtml(post.author_name)}</h3><p class="announcement-body">${escapeHtml(post.body)}</p><p class="user-meta">${escapeHtml(formatTimestamp(post.created_at))}</p></div><button class="quiet-button" type="button" data-remove-discussion="${post.id}">Remove</button></article>`).join("") : '<p class="empty-state">No member discussions yet.</p>';
  if (state.overview) renderOverview(state.overview);
};

$("#discussion-moderation-list").addEventListener("click", async (event) => {
  const button = event.target.closest("[data-remove-discussion]");
  if (!button) return;
  try { await request(`${API}/discussion/${button.dataset.removeDiscussion}`, { method: "DELETE" }); await loadDiscussions(); toast("Discussion post removed."); }
  catch (error) { toast(error.message); }
});

const renderBookSuggestions = () => {
  const pending = state.suggestions.filter((item) => item.status === "pending");
  $("#suggestion-queue-count").textContent = `${pending.length} awaiting review`;
  $("#book-suggestion-list").innerHTML = state.suggestions.length ? state.suggestions.map((item) => {
    const actions = item.status === "pending" ? `<button class="secondary-button" type="button" data-accept-suggestion="${item.id}">Add to library</button><button class="quiet-button" type="button" data-dismiss-suggestion="${item.id}">Dismiss</button>` : "";
    const statusLabel = item.status === "accepted" ? "Added to library" : item.status;
    return `<article class="user-card reader-suggestion-card"><img src="${escapeHtml(item.cover_image_url || "/static/assets/library-tools-logo-classic.svg?v=2")}" alt="" /><div><div class="suggestion-card-heading"><div><h3>${escapeHtml(item.title)}</h3><p class="user-meta">${escapeHtml(item.author)} · suggested by ${escapeHtml(item.proposed_by_name || "a reader")}</p></div><span class="status${item.status === "dismissed" ? " disabled" : ""}">${escapeHtml(statusLabel)}</span></div>${item.comments ? `<blockquote><span>Reader comment</span>${escapeHtml(item.comments)}</blockquote>` : '<p class="suggestion-no-comment">No comment was included.</p>'}</div><div class="user-actions">${actions}</div></article>`;
  }).join("") : '<p class="empty-state">Reader suggestions will appear here, even when no book vote is open.</p>';
};
const loadBookSuggestions = async () => { state.suggestions = await request(`${API}/book-suggestions`); renderBookSuggestions(); if (state.overview) renderOverview(state.overview); };
$("#book-suggestion-list").addEventListener("click", async (event) => {
  const accept = event.target.closest("[data-accept-suggestion]");
  const dismiss = event.target.closest("[data-dismiss-suggestion]");
  if (!accept && !dismiss) return;
  const action = accept ? "accept" : "dismiss";
  const id = (accept || dismiss).dataset[accept ? "acceptSuggestion" : "dismissSuggestion"];
  try {
    await request(`${API}/book-suggestions/${id}/${action}`, { method: "POST" });
    state.books = await request(`${API}/books?limit=500`);
    await Promise.all([loadBookSuggestions(), loadOverview()]);
    toast(accept ? "Suggestion added to the club library." : "Suggestion dismissed.");
  } catch (error) { toast(error.message); }
});

const openAnnouncement = (item = null) => {
  const form = $("#announcement-form"); form.reset(); $("#announcement-error").textContent = "";
  $("#announcement-dialog-title").textContent = item ? "Edit announcement" : "New announcement";
  $("#delete-announcement").hidden = !item; form.elements.id.value = item?.id || "";
  if (item) { form.elements.title.value = item.title; form.elements.body.value = item.body; form.elements.pinned.checked = item.pinned; }
  $("#announcement-dialog").showModal();
};
$("#new-announcement").addEventListener("click", () => openAnnouncement());
$("[data-new-announcement]").addEventListener("click", () => openAnnouncement());
$("#announcements-list").addEventListener("click", (event) => { const id = event.target.closest("[data-edit-announcement]")?.dataset.editAnnouncement; if (id) openAnnouncement(state.announcements.find((item) => String(item.id) === id)); });
$("#announcement-form").addEventListener("submit", async (event) => {
  event.preventDefault(); const form = event.currentTarget; const id = form.elements.id.value;
  const data = { title: form.elements.title.value, body: form.elements.body.value, pinned: form.elements.pinned.checked };
  try { await request(`${API}/announcements${id ? `/${id}` : ""}`, { method: id ? "PATCH" : "POST", body: JSON.stringify(data) }); $("#announcement-dialog").close(); await loadAnnouncements(); toast(id ? "Announcement updated." : "Announcement published."); }
  catch (error) { $("#announcement-error").textContent = error.message; }
});
$("#delete-announcement").addEventListener("click", async () => {
  const id = $("#announcement-form").elements.id.value; if (!id || !confirm("Delete this announcement?")) return;
  try { await request(`${API}/announcements/${id}`, { method: "DELETE" }); $("#announcement-dialog").close(); await loadAnnouncements(); toast("Announcement deleted."); } catch (error) { $("#announcement-error").textContent = error.message; }
});

const renderVotingCandidate = (candidate) => {
  const actions = candidate.status === "pending" ? `<button class="secondary-button" data-approve-candidate="${candidate.id}">Approve</button><button class="quiet-button" data-reject-candidate="${candidate.id}">Reject</button>` : "";
  return `<article class="user-card"><div><h3>${escapeHtml(candidate.book.title)}</h3><p class="user-meta">${escapeHtml(candidate.book.author)} · <span class="status${candidate.status === "rejected" ? " disabled" : ""}">${candidate.status}</span>${candidate.vote_count != null ? ` · ${candidate.vote_count} vote${candidate.vote_count === 1 ? "" : "s"}` : ""}${candidate.proposed_by_name ? ` · proposed by ${escapeHtml(candidate.proposed_by_name)}` : ""}</p></div><div class="user-actions">${actions}</div></article>`;
};
const renderVoting = (round) => {
  state.votingRound = round;
  if (state.overview) renderOverview(state.overview);
  if (!round) { $("#voting-toolbar-copy").textContent = "No poll is running. Start one when your club is ready to choose."; $("#start-voting-round").hidden = false; $("#close-voting-round").hidden = true; $("#add-candidate-row").hidden = true; $("#voting-list").innerHTML = '<p class="empty-state">Participants will vote and propose books here once you open a poll.</p>'; return; }
  const open = round.status === "open"; $("#voting-toolbar-copy").textContent = open ? "Voting is open. Review participant proposals and watch the response." : "This poll is closed."; $("#start-voting-round").hidden = open; $("#close-voting-round").hidden = !open;
  const used = new Set(round.candidates.map((candidate) => candidate.book.id)); const remaining = state.books.filter((book) => !used.has(book.id));
  $("#candidate-book-select").innerHTML = remaining.map((book) => `<option value="${book.id}">${escapeHtml(book.title)}</option>`).join(""); $("#add-candidate-row").hidden = !open || !remaining.length;
  const winner = !open && round.winning_book ? `<p class="muted">Selected: <strong>${escapeHtml(round.winning_book.title)}</strong></p>` : ""; $("#voting-list").innerHTML = winner + round.candidates.map(renderVotingCandidate).join("");
};
const loadVoting = async () => { try { renderVoting(await request(`${API}/voting-round`)); } catch (error) { if (error.status === 404) renderVoting(null); else toast(error.message); } };
$("#start-voting-round").addEventListener("click", () => { $("#start-voting-error").textContent = ""; $("#start-voting-choices").innerHTML = state.books.length ? state.books.map((book) => `<label><input type="checkbox" name="candidate_book_ids" value="${book.id}" /> ${escapeHtml(book.title)}</label>`).join("") : '<p class="muted">Add books on the Books page first.</p>'; $("#start-voting-dialog").showModal(); });
$("#start-voting-form").addEventListener("submit", async (event) => { event.preventDefault(); const ids = $$("#start-voting-choices input:checked").map((input) => Number(input.value)); try { renderVoting(await request(`${API}/voting-round`, { method: "POST", body: JSON.stringify({ candidate_book_ids: ids }) })); $("#start-voting-dialog").close(); await loadOverview(); toast("Voting opened."); } catch (error) { $("#start-voting-error").textContent = error.message; } });
$("#add-candidate-button").addEventListener("click", async () => { const value = $("#candidate-book-select").value; if (!value) return; try { await request(`${API}/voting-round/candidates`, { method: "POST", body: JSON.stringify({ book_id: Number(value) }) }); await loadVoting(); toast("Candidate added."); } catch (error) { toast(error.message); } });
$("#voting-list").addEventListener("click", async (event) => { const approve = event.target.closest("[data-approve-candidate]"); const reject = event.target.closest("[data-reject-candidate]"); if (!approve && !reject) return; const id = (approve || reject).dataset[approve ? "approveCandidate" : "rejectCandidate"]; try { renderVoting(await request(`${API}/candidates/${id}/${approve ? "approve" : "reject"}`, { method: "POST" })); await loadOverview(); } catch (error) { toast(error.message); } });
$("#close-voting-round").addEventListener("click", async () => { if (!confirm("Close voting and select the leading book?")) return; try { renderVoting(await request(`${API}/voting-round/close`, { method: "POST" })); toast("Voting closed."); } catch (error) { toast(error.message); } });

const renderDatePoll = (poll) => {
  state.datePoll = poll;
  if (state.overview) renderOverview(state.overview);
  if (!poll) { $("#date-poll-toolbar-copy").textContent = "No date poll is running. Start one when you have options to propose."; $("#start-date-poll").hidden = false; $("#close-date-poll").hidden = true; $("#add-date-option-row").hidden = true; $("#date-poll-list").innerHTML = '<p class="empty-state">Date options and participant responses will appear here.</p>'; return; }
  const open = poll.status === "open"; $("#date-poll-toolbar-copy").textContent = open ? "Voting is open. Add another option if plans change." : "This date poll is closed."; $("#start-date-poll").hidden = open; $("#close-date-poll").hidden = !open; $("#add-date-option-row").hidden = !open;
  const winner = !open && poll.winning_date ? `<p class="muted">Selected: <strong>${escapeHtml(formatDate(poll.winning_date))}</strong></p>` : ""; $("#date-poll-list").innerHTML = winner + poll.options.map((option) => `<article class="user-card"><div><h3>${escapeHtml(formatDate(option.option_date))}</h3><p class="user-meta">${option.vote_count ?? 0} vote${option.vote_count === 1 ? "" : "s"}</p></div></article>`).join("");
};
const loadDatePoll = async () => { try { renderDatePoll(await request(`${API}/date-poll`)); } catch (error) { if (error.status === 404) renderDatePoll(null); else toast(error.message); } };
$("#start-date-poll").addEventListener("click", () => { $("#start-date-poll-form").reset(); $("#start-date-poll-error").textContent = ""; $("#start-date-poll-dialog").showModal(); });
$("#start-date-poll-form").addEventListener("submit", async (event) => { event.preventDefault(); const dates = $$("#start-date-poll-form input[name=option_dates]").map((input) => input.value).filter(Boolean); try { renderDatePoll(await request(`${API}/date-poll`, { method: "POST", body: JSON.stringify({ option_dates: dates }) })); $("#start-date-poll-dialog").close(); toast("Date poll opened."); } catch (error) { $("#start-date-poll-error").textContent = error.message; } });
$("#add-date-option-button").addEventListener("click", async () => { const input = $("#date-option-input"); if (!input.value) return; try { renderDatePoll(await request(`${API}/date-poll/options`, { method: "POST", body: JSON.stringify({ option_date: input.value }) })); input.value = ""; toast("Date added."); } catch (error) { toast(error.message); } });
$("#close-date-poll").addEventListener("click", async () => { if (!confirm("Close the poll and select the leading date?")) return; try { renderDatePoll(await request(`${API}/date-poll/close`, { method: "POST" })); toast("Date poll closed."); } catch (error) { toast(error.message); } });

$("#logout").addEventListener("click", async () => { await request("/auth/logout", { method: "POST" }); location.href = "/login"; });
(async () => { try { const user = await request("/auth/me"); const club = await request("/bookclub/clubs/selected"); applyManagerShell(user, club); document.title = `${club.name} — Community`; state.books = await request(`${API}/books?limit=500`); await Promise.all([loadOverview(), loadVoting(), loadBookSuggestions(), loadDatePoll(), loadAnnouncements(), loadDiscussions()]); renderOverview(state.overview); } catch { location.href = "/bookclub"; } })();
