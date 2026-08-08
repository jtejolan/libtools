const $ = (selector) => document.querySelector(selector);

const pathParts = location.pathname.split("/").filter(Boolean);
// /clubs/{slug}/join, /clubs/{slug}/login, /clubs/{slug}/forgot-password
// all carry the slug in the path; /verify-email and /reset-password don't
// need one, since a token alone identifies the participant (and club).
const slug = pathParts[0] === "clubs" ? decodeURIComponent(pathParts[1] || "") : "";

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

const authCards = ["create-club", "join", "participant-login", "forgot", "reset", "verify"];
const showAuthCard = (name) => {
  authCards.forEach((card) => {
    $(`#${card}-card`).hidden = card !== name;
  });
};

const loadClubHeader = async () => {
  if (!slug) return null;
  try {
    const club = await request(`/api/public/clubs/${encodeURIComponent(slug)}`);
    document.title = `${club.name} — Book Club`;
    $("#club-eyebrow").textContent = club.name;
    $("#club-heading").textContent = "Join the conversation.";
    $("#club-description").textContent = club.description || "Rate what you've read and vote on what's next.";
    return club;
  } catch {
    $("#club-heading").textContent = "Club not found";
    $("#club-description").textContent = "This club page is unavailable or private.";
    return null;
  }
};

$("#create-club-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  $("#create-club-error").textContent = "";
  try {
    await request("/participant/clubs", {
      method: "POST",
      body: JSON.stringify(Object.fromEntries(new FormData(form))),
    });
    location.href = "/dashboard";
  } catch (error) {
    $("#create-club-error").textContent = error.message;
  }
});

$("#join-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  $("#join-error").textContent = "";
  try {
    await request("/participant/auth/register", {
      method: "POST",
      body: JSON.stringify({ club_slug: slug, ...Object.fromEntries(new FormData(form)) }),
    });
    location.href = "/dashboard";
  } catch (error) {
    $("#join-error").textContent = error.message;
  }
});

$("#participant-login-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  $("#participant-login-error").textContent = "";
  try {
    await request("/participant/auth/login", {
      method: "POST",
      body: JSON.stringify({ club_slug: slug, ...Object.fromEntries(new FormData(form)) }),
    });
    location.href = "/dashboard";
  } catch (error) {
    $("#participant-login-error").textContent = error.message;
  }
});

$("#forgot-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  $("#forgot-error").textContent = "";
  try {
    const result = await request("/participant/auth/password-reset/request", {
      method: "POST",
      body: JSON.stringify({ club_slug: slug, email: form.elements.email.value }),
    });
    const output = $("#forgot-result");
    output.hidden = false;
    output.innerHTML = `<strong>Request received.</strong><p>${escapeHtml(result.message)}</p>${result.delivery_configured ? "" : "<small>Email delivery is not connected yet for this club.</small>"}`;
    form.reset();
  } catch (error) {
    $("#forgot-error").textContent = error.message;
  }
});

$("#reset-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  $("#reset-error").textContent = "";
  try {
    const result = await request("/participant/auth/password-reset/confirm", {
      method: "POST",
      body: JSON.stringify(Object.fromEntries(new FormData(form))),
    });
    form.hidden = true;
    const output = $("#reset-result");
    output.hidden = false;
    output.innerHTML = `<strong>Password updated.</strong><p>You can now <a href="/clubs/${encodeURIComponent(result.club_slug)}/login">sign in with your new password</a>.</p>`;
  } catch (error) {
    $("#reset-error").textContent = error.message;
  }
});

const verifyEmail = async (token) => {
  showAuthCard("verify");
  if (!token) {
    $("#verify-heading").textContent = "Verification link missing";
    $("#verify-message").textContent = "Open the complete link from your verification email.";
    return;
  }
  try {
    const result = await request("/participant/auth/verify-email", {
      method: "POST",
      body: JSON.stringify({ token }),
    });
    $("#verify-heading").textContent = "Email verified";
    $("#verify-message").textContent = `${result.email} can now be used for password recovery.`;
    const output = $("#verify-result");
    output.hidden = false;
    output.innerHTML = '<a class="primary-button button-link full" href="/dashboard">Continue to your dashboard</a>';
  } catch (error) {
    $("#verify-heading").textContent = "Could not verify email";
    $("#verify-message").textContent = error.message;
  }
};

const initialize = async () => {
  const path = location.pathname;
  const params = new URLSearchParams(location.search);

  if (path === "/create") {
    document.title = "Start a club — Book Club";
    $("#club-eyebrow").textContent = "New club";
    $("#club-heading").textContent = "Bring your people together.";
    $("#club-description").textContent = "Pick a name, invite readers, and start choosing books.";
    showAuthCard("create-club");
    return;
  }
  if (path === "/verify-email") {
    await verifyEmail(params.get("token"));
    return;
  }
  if (path === "/reset-password") {
    showAuthCard("reset");
    $("#reset-form").elements.token.value = params.get("token") || "";
    if (!params.get("token")) {
      $("#reset-error").textContent = "Open the complete link from your password reset email.";
      $("#reset-form").querySelector("button").disabled = true;
    }
    return;
  }

  const club = await loadClubHeader();
  if (!club) return;

  $("#join-login-link").innerHTML = `Already have an account? <a href="/clubs/${encodeURIComponent(slug)}/login">Sign in</a>`;
  $("#login-join-link").innerHTML = `New to ${escapeHtml(club.name)}? <a href="/clubs/${encodeURIComponent(slug)}/join">Create an account</a>`;
  $("#forgot-login-link").innerHTML = `<a href="/clubs/${encodeURIComponent(slug)}/login">Back to sign in</a>`;
  $("#forgot-link").href = `/clubs/${encodeURIComponent(slug)}/forgot-password`;

  try {
    const me = await request("/participant/auth/me");
    if (me.club_slug === slug) {
      location.href = "/dashboard";
      return;
    }
  } catch {
    // Not signed in (or signed into a different club) — show the form below.
  }

  if (path.endsWith("/join")) showAuthCard("join");
  else if (path.endsWith("/forgot-password")) showAuthCard("forgot");
  else showAuthCard("participant-login");
};

initialize();
