const $ = (selector) => document.querySelector(selector);

const requestedNextPath = new URLSearchParams(window.location.search).get("next");
const nextPath = requestedNextPath?.startsWith("/") && !requestedNextPath.startsWith("//")
  ? requestedNextPath
  : "/dashboard";

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

const authCards = ["login", "signup", "forgot", "reset", "verify", "recovery"];
const showAuthCard = (name) => {
  $("#auth-view").hidden = false;
  $("#settings-view").hidden = true;
  authCards.forEach((card) => {
    $(`#${card}-card`).hidden = card !== name;
  });
};

const showRecoveryCode = (target, code, label = "Save this new recovery code now:") => {
  target.hidden = false;
  target.innerHTML = `<strong>${escapeHtml(label)}</strong><code>${escapeHtml(code)}</code><small>It will not be shown again.</small>`;
};

const showSettings = (user) => {
  $("#auth-view").hidden = true;
  $("#settings-view").hidden = false;
  $("#logout").hidden = false;
  $("#dashboard-link").hidden = false;
  $("#welcome-heading").textContent = `Welcome, ${capitalizeFirst(user.name)}`;
  $("#admin-link").hidden = user.role !== "admin";

  const status = $("#email-status");
  if (!user.email) {
    $("#account-email-copy").textContent = "No email address is attached to this account. Your recovery code and an administrator can still restore access.";
    status.textContent = "Not provided";
    status.className = "status muted";
  } else if (user.email_verified) {
    $("#account-email-copy").textContent = `${user.email} can be used for password-reset links.`;
    status.textContent = "Verified";
    status.className = "status";
  } else {
    $("#account-email-copy").textContent = `${user.email} is waiting to be verified before it can be used for password resets.`;
    status.textContent = "Verification pending";
    status.className = "status pending";
    $("#resend-verification").hidden = false;
  }
};

$("#forgot-use-code").addEventListener("click", () => showAuthCard("recovery"));

$("#login-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  $("#login-error").textContent = "";
  try {
    await request("/auth/login", {
      method: "POST",
      body: JSON.stringify({
        username: form.elements.username.value,
        password: form.elements.password.value,
      }),
    });
    location.href = nextPath;
  } catch (error) {
    $("#login-error").textContent = error.message;
  }
});

$("#signup-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  $("#signup-error").textContent = "";
  try {
    const result = await request("/auth/register", {
      method: "POST",
      body: JSON.stringify(Object.fromEntries(new FormData(form))),
    });
    $("#signup-form-view").hidden = true;
    $("#signup-result").hidden = false;
    showRecoveryCode(
      $("#signup-recovery-code"),
      result.recovery_code,
      "Your one-time account recovery code:",
    );
    if (result.email_verification_required) {
      const note = $("#signup-email-note");
      note.hidden = false;
      note.textContent = result.email_delivery_configured
        ? `A verification link was sent to ${result.email}.`
        : "Your verification is pending. Email delivery has not been connected yet, but you can continue using your account.";
    }
  } catch (error) {
    $("#signup-error").textContent = error.message;
  }
});

$("#forgot-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  $("#forgot-error").textContent = "";
  try {
    const result = await request("/auth/password-reset/request", {
      method: "POST",
      body: JSON.stringify({ email: form.elements.email.value }),
    });
    const output = $("#forgot-result");
    output.hidden = false;
    output.innerHTML = `<strong>Request received.</strong><p>${escapeHtml(result.message)}</p>${result.delivery_configured ? "" : "<small>Email delivery is not connected yet. Recovery codes and administrator-assisted resets still work.</small>"}`;
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
    await request("/auth/password-reset/confirm", {
      method: "POST",
      body: JSON.stringify(Object.fromEntries(new FormData(form))),
    });
    form.hidden = true;
    const output = $("#reset-result");
    output.hidden = false;
    output.innerHTML = '<strong>Password updated.</strong><p>You can now <a href="/login">sign in with your new password</a>.</p>';
  } catch (error) {
    $("#reset-error").textContent = error.message;
  }
});

$("#recovery-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  $("#recovery-error").textContent = "";
  try {
    const result = await request("/auth/recover", {
      method: "POST",
      body: JSON.stringify(Object.fromEntries(new FormData(form))),
    });
    showRecoveryCode($("#recovery-result"), result.recovery_code);
    form.reset();
  } catch (error) {
    $("#recovery-error").textContent = error.message;
  }
});

$("#password-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  $("#password-error").textContent = "";
  try {
    await request("/auth/password", {
      method: "PUT",
      body: JSON.stringify(Object.fromEntries(new FormData(form))),
    });
    form.reset();
    toast("Password changed.");
  } catch (error) {
    $("#password-error").textContent = error.message;
  }
});

$("#new-recovery-code").addEventListener("click", async () => {
  if (!confirm("Replace your current recovery code?")) return;
  const result = await request("/auth/recovery-code", { method: "POST" });
  showRecoveryCode($("#account-recovery-result"), result.recovery_code);
});

$("#resend-verification").addEventListener("click", async () => {
  try {
    const result = await request("/auth/email-verification/request", { method: "POST" });
    const note = $("#verification-delivery-note");
    note.hidden = false;
    note.textContent = result.delivery_configured
      ? "A fresh verification link was sent."
      : "A fresh link is ready, but email delivery has not been connected yet.";
  } catch (error) {
    toast(error.message);
  }
});

$("#logout").addEventListener("click", async () => {
  await request("/auth/logout", { method: "POST" });
  location.href = "/login";
});

const verifyEmail = async (token) => {
  showAuthCard("verify");
  if (!token) {
    $("#verify-heading").textContent = "Verification link missing";
    $("#verify-message").textContent = "Open the complete link from your verification email.";
    return;
  }
  try {
    const user = await request("/auth/verify-email", {
      method: "POST",
      body: JSON.stringify({ token }),
    });
    $("#verify-heading").textContent = "Email verified";
    $("#verify-message").textContent = `${user.email} can now be used for password recovery.`;
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

  try {
    const user = await request("/auth/me");
    if (path !== "/account") {
      location.href = "/dashboard";
      return;
    }
    showSettings(user);
  } catch (error) {
    if (path === "/account") {
      location.href = "/login";
      return;
    }
    if (error.status !== 401) toast(error.message);
    if (path === "/signup") showAuthCard("signup");
    else if (path === "/forgot-password") showAuthCard("forgot");
    else if (location.hash === "#recover") showAuthCard("recovery");
    else showAuthCard("login");
  }
};

initialize();
