const $ = (selector) => document.querySelector(selector);
const slug = decodeURIComponent(location.pathname.split("/").filter(Boolean).pop() || "");

const request = async (url, options = {}) => {
  const response = await fetch(url, { ...options, cache: "no-store" });
  if (response.status === 204) return null;
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw Object.assign(new Error(body.detail || "Something went wrong."), { status: response.status });
  return body;
};

const formatDate = (value) => new Intl.DateTimeFormat("en-CA", { weekday: "long", month: "long", day: "numeric", year: "numeric" }).format(new Date(`${value}T12:00:00`));
const formatShelfDate = (value) => value ? new Intl.DateTimeFormat("en-CA", { month: "short", year: "numeric" }).format(new Date(`${value}T12:00:00`)) : "Previously selected";
const initials = (name) => name.split(/\s+/).filter(Boolean).slice(0, 2).map((word) => word[0]).join("").toUpperCase();
const safeImageUrl = (value) => {
  if (!value) return "";
  try {
    const url = new URL(value);
    return ["http:", "https:"].includes(url.protocol) ? url.href : "";
  } catch {
    return "";
  }
};

const participantPath = (suffix) => `/clubs/${encodeURIComponent(slug)}/${suffix}`;

const renderShelf = (books) => {
  if (!books.length) return;
  $("#shelf-section").hidden = false;
  $("#shelf-grid").innerHTML = books.map((book) => {
    const cover = safeImageUrl(book.cover_image_url);
    return `<article class="shelf-item"><div class="shelf-cover">${cover ? `<img src="${escapeHtml(cover)}" alt="Cover of ${escapeHtml(book.title)}" loading="lazy" />` : `<span>${escapeHtml(initials(book.title))}</span>`}</div><div><strong>${escapeHtml(book.title)}</strong><small>${escapeHtml(book.author)}</small><time>${escapeHtml(formatShelfDate(book.meeting_date))}</time></div></article>`;
  }).join("");
};

const renderMeeting = (meeting) => {
  if (!meeting) return;
  const cover = safeImageUrl(meeting.book.cover_image_url);
  $("#current-book-card").hidden = false;
  $("#current-book-title").textContent = meeting.book.title;
  $("#current-book-author").textContent = `by ${meeting.book.author}`;
  $("#current-book-description").textContent = meeting.book.description || "The club’s next shared read.";
  const coverElement = $("#public-cover");
  if (cover) {
    const image = new Image();
    image.alt = `Cover of ${meeting.book.title}`;
    image.src = cover;
    coverElement.replaceChildren(image);
    coverElement.removeAttribute("aria-hidden");
  } else {
    coverElement.textContent = initials(meeting.book.title);
  }
  const facts = [
    `<div><span>Date</span><strong>${escapeHtml(formatDate(meeting.meeting_date))}</strong></div>`,
    meeting.meeting_time ? `<div><span>Time</span><strong>${escapeHtml(meeting.meeting_time)}</strong></div>` : "",
    meeting.location ? `<div><span>Location</span><strong>${escapeHtml(meeting.location)}</strong></div>` : "",
  ].join("");
  $("#meeting-details").innerHTML = `<div class="meeting-facts">${facts}</div><div class="calendar-actions"><a class="public-primary" href="${escapeHtml(meeting.ics_calendar_url)}">Add to calendar <span aria-hidden="true"><svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 15V3" /><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" /><path d="m7 10 5 5 5-5" /></svg></span></a><a class="public-secondary" href="${escapeHtml(meeting.google_calendar_url)}" target="_blank" rel="noopener">Google Calendar <span aria-hidden="true"><svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 3h6v6" /><path d="M10 14 21 3" /><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" /></svg></span></a></div>`;
};

const enrollmentCopy = {
  open: { badge: "Open to readers", message: "This invitation is all you need." },
  invite_only: { badge: "Invitation only", message: "Use your roster email to join." },
  closed: { badge: "Membership closed", message: "New accounts are not being accepted." },
};

const setLinkAction = (element, label, handler) => {
  element.hidden = false;
  element.href = "#";
  element.innerHTML = `${escapeHtml(label)} <span aria-hidden="true"><svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m9 18 6-6-6-6" /></svg></span>`;
  element.onclick = async (event) => {
    event.preventDefault();
    $("#membership-error").textContent = "";
    element.classList.add("is-busy");
    try {
      await handler();
    } catch (error) {
      $("#membership-error").textContent = error.message;
      element.classList.remove("is-busy");
    }
  };
};

const configureMembership = async (club) => {
  const panel = $("#membership-panel");
  const primary = $("#join-club-link");
  const secondary = $("#participant-login-link");
  const copy = enrollmentCopy[club.enrollment_policy] || enrollmentCopy.open;
  $("#enrollment-badge").textContent = copy.badge;
  $("#membership-message").textContent = copy.message;
  primary.hidden = club.enrollment_policy === "closed";
  primary.onclick = null;
  primary.href = participantPath("join");
  primary.innerHTML = `${club.enrollment_policy === "invite_only" ? "Activate your invitation" : "Join this club"} <span aria-hidden="true"><svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m9 18 6-6-6-6" /></svg></span>`;
  secondary.href = participantPath("login");
  secondary.textContent = "Participant sign in";
  panel.hidden = false;

  try {
    await request("/participant/auth/me");
    const clubs = await request("/participant/auth/clubs");
    const membership = clubs.find((item) => item.slug === slug);
    if (membership) {
      setLinkAction(primary, "Open participant dashboard", async () => {
        await request(`/participant/auth/clubs/${encodeURIComponent(slug)}/select`, { method: "POST" });
        location.href = "/dashboard";
      });
      $("#enrollment-badge").textContent = "You’re a member";
      $("#membership-message").textContent = "Your reader space is ready.";
      secondary.href = "/";
      secondary.textContent = "View all my clubs";
      return;
    }
    if (club.enrollment_policy !== "closed") {
      setLinkAction(primary, club.enrollment_policy === "invite_only" ? "Accept invitation" : "Join this club", async () => {
        await request(`/participant/auth/clubs/${encodeURIComponent(slug)}/join`, { method: "POST" });
        location.href = "/dashboard";
      });
      secondary.href = "/";
      secondary.textContent = "View my other clubs";
    } else {
      secondary.href = "/";
      secondary.textContent = "View my clubs";
    }
  } catch {
    // Signed-out visitors keep the registration and club-specific sign-in actions.
  }
};

const showUnavailable = () => {
  $("#club-name").textContent = "Club not found";
  $("#club-description").textContent = "This club page is unavailable or private.";
  $("#meeting-section").hidden = true;
  $("#account-benefits").hidden = true;
};

(async () => {
  try {
    const club = await request(`/api/public/clubs/${encodeURIComponent(slug)}`);
    document.title = `${club.name} — Book Club`;
    $("#club-name").textContent = club.name;
    $("#club-description").textContent = club.description || "A community built around good books and lively conversations.";
    const organizer = [club.organizer_name, club.organizer_branch].filter(Boolean).join(" · ");
    if (organizer) {
      $("#organizer-line").hidden = false;
      $("#organizer-line").textContent = `Hosted by ${organizer}`;
      $("#club-context").textContent = club.organizer_branch || "Your reading community";
    }
    renderMeeting(club.upcoming_meeting);
    renderShelf(club.shelf || []);
    await configureMembership(club);
  } catch {
    showUnavailable();
  }
})();
