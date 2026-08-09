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

const token = new URLSearchParams(location.search).get("token");

if (!token) {
  $("#unsubscribe-message").textContent = "This link is missing its token — open the complete link from your email.";
} else {
  $("#unsubscribe-message").textContent = "Confirm below to stop receiving these emails. This does not remove your book club account or its votes/ratings.";
  $("#unsubscribe-card").hidden = false;
}

$("#confirm-unsubscribe").addEventListener("click", async () => {
  $("#unsubscribe-error").textContent = "";
  try {
    const result = await request("/participant/unsubscribe", {
      method: "POST",
      body: JSON.stringify({ token }),
    });
    $("#unsubscribe-card").hidden = true;
    $("#unsubscribe-result").hidden = false;
    $("#unsubscribe-result-heading").textContent = result.already_unsubscribed
      ? "Already unsubscribed"
      : "You're unsubscribed";
    $("#unsubscribe-result-message").textContent =
      `${result.email} will no longer receive broadcast emails from ${result.club_name}.`;
  } catch (error) {
    $("#unsubscribe-error").textContent = error.message;
  }
});
