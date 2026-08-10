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
    const message = typeof detail === "string" ? detail : detail?.[0]?.msg || "Something went wrong.";
    const error = new Error(message);
    error.status = response.status;
    throw error;
  }
  return body;
};

const goToLogin = () => {
  window.location.href = `/login?next=${encodeURIComponent("/bookclub/new")}`;
};

const form = $("#club-form");
const errorLine = $("#club-error");

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  errorLine.textContent = "";
  const submitButton = form.querySelector("button[type=submit]");
  submitButton.disabled = true;
  try {
    const club = await request("/bookclub/clubs", {
      method: "POST",
      body: JSON.stringify({
        name: form.elements.name.value.trim(),
        club_type: form.elements.club_type.value,
        organizer_name: form.elements.organizer_name.value.trim() || null,
        organizer_branch: form.elements.organizer_branch.value.trim() || null,
      }),
    });
    await request(`/bookclub/clubs/${club.id}/select`, { method: "POST" });
    window.location.href = "/bookclub";
  } catch (error) {
    if (error.status === 401) return goToLogin();
    errorLine.textContent = error.message;
    submitButton.disabled = false;
  }
});

(async () => {
  try {
    await request("/auth/me");
  } catch (error) {
    if (error.status === 401) goToLogin();
  }
})();
