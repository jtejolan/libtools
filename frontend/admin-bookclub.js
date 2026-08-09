const $ = (selector) => document.querySelector(selector);

const request = async (url, options = {}) => {
  const response = await fetch(url, { ...options, cache: "no-store" });
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

const formatDate = (value) => {
  if (!value) return "Unknown";
  return new Date(value).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
};

const render = (clubs) => {
  $("#club-total").textContent = clubs.length;
  $("#participant-total").textContent = clubs.reduce((sum, club) => sum + club.participant_count, 0);
  $("#club-list").innerHTML = clubs.length
    ? clubs.map((club) => `
      <article class="user-card">
        <div class="account-identity">
          <div><h3>${escapeHtml(club.name)}</h3><p class="user-meta">bookclub.libtools.app/clubs/${escapeHtml(club.slug)}</p></div>
          <span class="status">${club.participant_count} ${club.participant_count === 1 ? "participant" : "participants"}</span>
        </div>
        <div class="account-contact">
          <span class="user-meta">Facilitator: ${club.facilitator_name ? escapeHtml(club.facilitator_name) : "None"}${club.facilitator_email ? ` (${escapeHtml(club.facilitator_email)})` : ""}</span>
          <span class="user-meta">Created ${formatDate(club.created_at)}</span>
        </div>
      </article>`).join("")
    : '<div class="accounts-empty"><strong>No self-serve clubs yet</strong><span>Clubs created on bookclub.libtools.app will show up here.</span></div>';
};

const load = async () => {
  try {
    render(await request("/api/admin/bookclub/self-serve-clubs"));
  } catch (error) {
    toast(error.message);
  }
};

$("#logout").addEventListener("click", async () => {
  await request("/auth/logout", { method: "POST" });
  location.href = "/login";
});

(async () => {
  try {
    const me = await request("/auth/me");
    if (me.role !== "admin") location.href = "/dashboard";
    else await load();
  } catch {
    location.href = "/login";
  }
})();
