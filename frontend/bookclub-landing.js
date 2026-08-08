const $ = (s) => document.querySelector(s);

// Facilitators are ParticipantAccounts (role=owner), fully segmented from
// the general libtools.app account system — see docs/backend/bookclub.md.
// "Start a club" stays entirely on this subdomain.
$("#start-club-link").href = "/create";

$("#find-club-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const raw = $("#club-slug-input").value.trim();
  const slug = raw
    .toLowerCase()
    .replace(/^https?:\/\/[^/]+\/?(clubs\/)?/, "")
    .replace(/\/+$/, "");
  if (!slug) {
    $("#find-club-error").textContent = "Enter a club address to continue.";
    return;
  }
  location.href = `/clubs/${encodeURIComponent(slug)}`;
});
