const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const API = "/bookclub/community";
const PARTICIPANT_PORTAL_ORIGIN = "https://bookclub.libtools.app";
const state = { books: [], announcements: [], overview: null, club: null };

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
  ["overview", "voting", "date-poll", "announcements"].forEach((name) => { $(`#${name}-view`).hidden = name !== view; });
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
$$("[data-copy-invite]").forEach((button) => button.addEventListener("click", async () => {
  const value = button.dataset.copyInvite === "code" ? state.club?.slug : participantInviteUrl(state.club);
  try {
    await copyText(value);
    toast(button.dataset.copyInvite === "code" ? "Club code copied." : "Invitation link copied.");
  } catch (error) {
    toast(error.message);
  }
}));

const activationLabel = (status) => ({ active: "Community active", pending_verification: "Verification pending", not_registered: "Invitation not accepted", account_disabled: "Account disabled" })[status] || status;
const activationClass = (status) => status === "active" ? "" : status === "pending_verification" ? "pending" : status === "account_disabled" ? "disabled" : "unlinked";
const rsvpLabel = (status) => ({ attending: "Attending", maybe: "Maybe", not_attending: "Can’t attend" })[status] || "No RSVP";

const renderOverview = (overview) => {
  state.overview = overview;
  $("#member-count").textContent = overview.member_count;
  $("#linked-count").textContent = overview.linked_account_count;
  $("#verified-count").textContent = overview.verified_account_count;
  const attention = overview.pending_verification_count + overview.disabled_account_count + overview.unlinked_member_count + overview.pending_book_proposals;
  $("#attention-count").textContent = attention;

  const meeting = overview.next_meeting;
  if (!meeting) {
    $("#next-meeting-heading").textContent = "No upcoming meeting";
    $("#next-meeting-content").innerHTML = '<p>Schedule the next gathering on the Meetings page.</p><a class="secondary-button" href="/bookclub">Open meetings</a>';
  } else {
    $("#next-meeting-heading").textContent = meeting.book.title;
    const counts = overview.rsvp_counts;
    $("#next-meeting-content").innerHTML = `<p>${escapeHtml(formatDate(meeting.meeting_date))}${meeting.meeting_time ? ` · ${escapeHtml(meeting.meeting_time)}` : ""}${meeting.location ? ` · ${escapeHtml(meeting.location)}` : ""}</p><div class="rsvp-strip"><span class="rsvp-count"><strong>${counts.attending}</strong> attending</span><span class="rsvp-count"><strong>${counts.maybe}</strong> maybe</span><span class="rsvp-count"><strong>${counts.not_attending}</strong> can’t attend</span><span class="rsvp-count"><strong>${counts.no_response}</strong> no response</span></div>`;
  }

  const queue = [];
  if (overview.pending_book_proposals) queue.push(`<button class="quiet-button" data-open-view="voting">${overview.pending_book_proposals} book proposal${overview.pending_book_proposals === 1 ? "" : "s"} to review</button>`);
  if (overview.pending_verification_count) queue.push(`<p><strong>${overview.pending_verification_count}</strong> account${overview.pending_verification_count === 1 ? "" : "s"} awaiting email verification</p>`);
  if (overview.disabled_account_count) queue.push(`<p><strong>${overview.disabled_account_count}</strong> community account${overview.disabled_account_count === 1 ? " is" : "s are"} disabled</p>`);
  if (overview.unlinked_member_count) queue.push(`<p><strong>${overview.unlinked_member_count}</strong> invitation${overview.unlinked_member_count === 1 ? " has" : "s have"} not been accepted</p>`);
  $("#attention-list").innerHTML = queue.length ? queue.join("") : '<p class="muted">Nothing needs your attention right now.</p>';

  $("#activation-list").innerHTML = overview.accounts.length ? overview.accounts.map((account) => `<div class="activation-row"><div><strong>${escapeHtml(account.name)}</strong><div class="user-meta">${escapeHtml(account.email)}</div></div><div class="activation-statuses"><span class="status-pill ${activationClass(account.status)}">${activationLabel(account.status)}</span>${meeting ? `<span class="status-pill rsvp">${rsvpLabel(account.rsvp_status)}</span>` : ""}</div></div>`).join("") : '<p class="empty-state">No active roster members yet.</p>';
};

const loadOverview = async () => renderOverview(await request(`${API}/overview`));
$("#attention-list").addEventListener("click", (event) => { const view = event.target.closest("[data-open-view]")?.dataset.openView; if (view) selectView(view); });

const renderAnnouncements = () => {
  $("#announcements-list").innerHTML = state.announcements.length ? state.announcements.map((item) => `<article class="user-card announcement-card"><div>${item.pinned ? '<div class="pin-mark">Pinned</div>' : ""}<h3>${escapeHtml(item.title)}</h3><p class="user-meta">Published ${escapeHtml(formatTimestamp(item.published_at))}</p><p class="announcement-body">${escapeHtml(item.body)}</p></div><div class="user-actions"><button class="quiet-button" data-edit-announcement="${item.id}">Edit</button></div></article>`).join("") : '<p class="empty-state">No announcements yet. Publish a welcome message or an update about the next discussion.</p>';
};
const loadAnnouncements = async () => { state.announcements = await request(`${API}/announcements`); renderAnnouncements(); };
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
(async () => { try { const user = await request("/auth/me"); const club = await request("/bookclub/clubs/selected"); applyManagerShell(user, club); document.title = `${club.name} — Community`; state.books = await request(`${API}/books?limit=500`); await Promise.all([loadOverview(), loadVoting(), loadDatePoll(), loadAnnouncements()]); } catch { location.href = "/bookclub"; } })();
