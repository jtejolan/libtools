const $ = (s) => document.querySelector(s);

// Club creation and management live in the full Libtools account product;
// this subdomain is the participant portal only.
$("#start-club-link").href = "https://libtools.app/signup?next=/bookclub";

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
