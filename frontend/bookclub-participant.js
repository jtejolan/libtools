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
  } catch {
    location.href = "/";
  }
})();
