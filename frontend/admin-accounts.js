const $ = (selector) => document.querySelector(selector);
let users = [];
let query = "";

const escapeHtml = (value = "") =>
  String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");

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

const showCode = (target, code) => {
  target.hidden = false;
  target.innerHTML = `<strong>Save this recovery code now:</strong><code>${escapeHtml(code)}</code><small>It will not be shown again.</small>`;
};

const emailSummary = (user) => {
  if (!user.email) return '<span class="account-email muted">No email</span>';
  return `<span class="account-email">${escapeHtml(user.email)}</span><span class="status ${user.email_verified ? "" : "pending"}">${user.email_verified ? "Email verified" : "Verification pending"}</span>`;
};

const visibleUsers = () => {
  const needle = query.trim().toLocaleLowerCase();
  if (!needle) return users;
  return users.filter((user) => [user.name, user.username, user.email || ""].some((value) => value.toLocaleLowerCase().includes(needle)));
};

const render = () => {
  const activeCount = users.filter((user) => user.active).length;
  const pendingCount = users.filter((user) => user.email && !user.email_verified).length;
  $("#account-total").textContent = users.length;
  $("#account-active").textContent = activeCount;
  $("#email-pending").textContent = pendingCount;
  const shown = visibleUsers();
  $("#user-count").textContent = query ? `${shown.length} of ${users.length} accounts` : `${users.length} ${users.length === 1 ? "account" : "accounts"}`;
  $("#user-list").innerHTML = shown.length
    ? shown.map((user) => `
      <article class="user-card account-card" data-user-id="${user.id}">
        <div class="account-identity">
          <div><h3>${escapeHtml(capitalizeFirst(user.name))}</h3><p class="user-meta">@${escapeHtml(user.username)}</p></div>
          <span class="status ${user.active ? "" : "disabled"}">${user.active ? user.role : "Disabled"}</span>
        </div>
        <div class="account-contact">${emailSummary(user)}<span class="user-meta">Clubs: ${escapeHtml(user.clubs.join(", ") || "None")}</span></div>
        <div class="user-actions account-actions"><button class="quiet-button" data-reset>Reset password</button><button class="quiet-button" data-recovery>New recovery code</button><button class="secondary-button" data-toggle>${user.active ? "Disable" : "Restore"}</button></div>
        <div class="user-permissions account-permissions">
          <label class="field account-name-field"><span>Name</span><input data-name maxlength="200" value="${escapeHtml(user.name)}" /></label>
          <label class="field"><span>Role</span><select data-role><option value="user" ${user.role === "user" ? "selected" : ""}>User</option><option value="admin" ${user.role === "admin" ? "selected" : ""}>Administrator</option></select></label>
          <fieldset class="access-fieldset inline-access"><legend>Additional permission</legend><label><input type="checkbox" data-tool="lendery_manage" ${user.tools.includes("lendery_manage") ? "checked" : ""} /> Edit Lendery inventory</label></fieldset>
          <button class="secondary-button save-account" data-save>Save changes</button>
        </div>
      </article>`).join("")
    : '<div class="accounts-empty"><strong>No matching accounts</strong><span>Try a different name, username, or email.</span></div>';
};

const load = async () => {
  users = await request("/api/admin/users");
  render();
};

$("#account-search").addEventListener("input", (event) => {
  query = event.target.value;
  render();
});

$("#create-user-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  $("#create-error").textContent = "";
  try {
    const account = await request("/api/admin/users", {
      method: "POST",
      body: JSON.stringify({
        name: form.elements.name.value,
        username: form.elements.username.value,
        email: form.elements.email.value,
        password: form.elements.password.value,
        confirm_password: form.elements.confirm_password.value,
        role: form.elements.role.value,
        tools: [
          ...(form.elements.lendery_manage.checked ? ["lendery_manage"] : []),
        ],
      }),
    });
    showCode($("#created-result"), account.recovery_code);
    form.reset();
    await load();
    toast("Account created.");
  } catch (error) {
    $("#create-error").textContent = error.message;
  }
});

$("#user-list").addEventListener("click", async (event) => {
  const card = event.target.closest("[data-user-id]");
  if (!card) return;
  const user = users.find((entry) => entry.id === Number(card.dataset.userId));
  try {
    if (event.target.closest("[data-toggle]")) {
      await request(`/api/admin/users/${user.id}`, { method: "PATCH", body: JSON.stringify({ active: !user.active }) });
      await load();
    } else if (event.target.closest("[data-save]")) {
      const tools = [...card.querySelectorAll("[data-tool]:checked")].map((input) => input.dataset.tool);
      await request(`/api/admin/users/${user.id}`, { method: "PATCH", body: JSON.stringify({ name: card.querySelector("[data-name]").value, role: card.querySelector("[data-role]").value, tools }) });
      await load();
      toast("Account updated.");
    } else if (event.target.closest("[data-recovery]")) {
      if (!confirm(`Replace ${capitalizeFirst(user.name)}'s recovery code?`)) return;
      const result = await request(`/api/admin/users/${user.id}/recovery-code`, { method: "POST" });
      showCode($("#created-result"), result.recovery_code);
      window.scrollTo({ top: 0, behavior: "smooth" });
    } else if (event.target.closest("[data-reset]")) {
      const form = $("#reset-form");
      form.reset();
      form.elements.user_id.value = user.id;
      $("#reset-title").textContent = `Reset ${capitalizeFirst(user.name)}'s password`;
      $("#reset-result").hidden = true;
      $("#reset-dialog").showModal();
    }
  } catch (error) {
    toast(error.message);
  }
});

$("#reset-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  $("#reset-error").textContent = "";
  try {
    const result = await request(`/api/admin/users/${form.elements.user_id.value}/password`, { method: "POST", body: JSON.stringify({ password: form.elements.password.value, confirm_password: form.elements.confirm_password.value }) });
    showCode($("#reset-result"), result.recovery_code);
    form.elements.password.value = "";
    form.elements.confirm_password.value = "";
  } catch (error) {
    $("#reset-error").textContent = error.message;
  }
});

$("#close-reset").addEventListener("click", () => $("#reset-dialog").close());
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
