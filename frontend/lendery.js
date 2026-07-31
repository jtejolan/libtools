const state = {
  user: null,
  items: [],
  query: "",
  category: "",
  availabilityFilter: "",
  availabilitySort: "",
  selectedId: null,
  checkedComponents: new Set(),
  refreshingIds: new Set(),
  refreshPromises: new Map(),
};

const AVAILABILITY_STALE_MS = 30 * 60 * 1000;
const AUTO_REFRESH_CONCURRENCY = 3;
const AVAILABILITY_STATUS_VERSION = 2;

const grid = document.querySelector("#inventory-grid");
const filters = document.querySelector("#category-filters");
const availabilityFilters = document.querySelector("#availability-filters");
const availabilitySort = document.querySelector("#availability-sort");
const searchInput = document.querySelector("#search-input");
const dialog = document.querySelector("#item-dialog");
const itemForm = document.querySelector("#item-form");
const formError = document.querySelector("#form-error");
const drawer = document.querySelector("#item-drawer");
const drawerContent = document.querySelector("#drawer-content");
const drawerBackdrop = document.querySelector("#drawer-backdrop");
const toast = document.querySelector("#toast");
const loginDialog = document.querySelector("#login-dialog");
const loginForm = document.querySelector("#login-form");
const loginError = document.querySelector("#login-error");
const passwordDialog = document.querySelector("#password-dialog");
const passwordForm = document.querySelector("#password-form");
const passwordError = document.querySelector("#password-error");
const accountActions = document.querySelector("#account-actions");
const roleBadge = document.querySelector("#role-badge");

const escapeHtml = (value = "") =>
  String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");

const safeUrl = (value) => {
  if (!value) return "";
  try {
    const url = new URL(value, window.location.origin);
    return ["http:", "https:"].includes(url.protocol) ? url.href : "";
  } catch {
    return "";
  }
};

const request = async (url, options = {}) => {
  const response = await fetch(url, {
    ...options,
    headers: {
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...options.headers,
    },
  });

  if (response.status === 204) return null;
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const message =
      typeof body.detail === "string"
        ? body.detail
        : body.detail?.[0]?.msg || "Something went wrong.";
    const error = new Error(message);
    error.status = response.status;
    if (response.status === 401 && !url.endsWith("/auth/login")) {
      showLogin();
    }
    throw error;
  }
  return body;
};

const isAdmin = () => state.user?.role === "admin";

const applyUser = (user) => {
  state.user = user;
  accountActions.hidden = false;
  roleBadge.textContent = user.role === "admin" ? "Administrator" : "Clerk";
  document.querySelectorAll("[data-admin-only]").forEach((element) => {
    element.hidden = !isAdmin();
  });
};

const showLogin = () => {
  state.user = null;
  accountActions.hidden = true;
  closeDrawer();
  if (dialog.open) dialog.close();
  if (passwordDialog.open) passwordDialog.close();
  if (!loginDialog.open) loginDialog.showModal();
};

const showToast = (message) => {
  toast.textContent = message;
  toast.classList.add("show");
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => toast.classList.remove("show"), 2600);
};

const itemInitials = (name) =>
  name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((word) => word[0])
    .join("")
    .toUpperCase();

const availabilityInfo = (item) => {
  if (!item.library_url) {
    return {
      status: "not-linked",
      shortLabel: "Not linked",
      label: "No catalogue record",
      description: "Add a Vaughan library catalogue URL to track this item.",
    };
  }

  if (state.refreshingIds.has(item.id)) {
    return {
      status: "checking",
      shortLabel: "Checking",
      label: "Checking Pierre Berton availability",
      description: "Getting the latest copy status from the catalogue.",
    };
  }

  return {
    available: {
      status: "available",
      shortLabel: "In",
      label: "Available at Pierre Berton",
      description:
        item.available_copies === null
          ? "At least one copy is available."
          : `${item.available_copies} of ${item.total_copies_at_branch} ${
              item.total_copies_at_branch === 1 ? "copy is" : "copies are"
            } currently available.`,
    },
    checked_out: {
      status: "checked-out",
      shortLabel: "Out",
      label: "All Pierre Berton copies are out",
      description: `${item.total_copies_at_branch ?? "All"} ${
        item.total_copies_at_branch === 1 ? "copy is" : "copies are"
      } currently in use.`,
    },
    unavailable: {
      status: "unavailable",
      shortLabel: "Unavailable",
      label: "Unavailable at Pierre Berton",
      description:
        "The catalogue does not list a borrowable copy. It may be damaged, under repair, or otherwise unavailable.",
    },
    not_held: {
      status: "not-held",
      shortLabel: "Not held",
      label: "Not held at Pierre Berton",
      description: "No Pierre Berton copies appear on this catalogue record.",
    },
    unknown: {
      status: "unknown",
      shortLabel: "Unknown",
      label: "Availability unknown",
      description: "Open or refresh this item to check the catalogue.",
    },
  }[item.availability_status || "unknown"];
};

const formatCheckedAt = (value) => {
  if (!value) return "Not checked yet";
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? "Check time unavailable"
    : `Checked ${date.toLocaleString()}`;
};

const visibleItems = () => {
  const query = state.query.toLowerCase().trim();
  const items = state.items.filter((item) => {
    const matchesCategory = !state.category || item.category === state.category;
    const matchesAvailability =
      !state.availabilityFilter ||
      item.availability_status === state.availabilityFilter;
    const matchesQuery =
      !query ||
      [item.name, item.barcode, item.category, item.description]
        .filter(Boolean)
        .some((value) => value.toLowerCase().includes(query));
    return matchesCategory && matchesAvailability && matchesQuery;
  });

  if (!state.availabilitySort) return items;

  const availableFirst = {
    available: 0,
    checked_out: 1,
    unavailable: 2,
    not_held: 3,
    unknown: 4,
  };
  const checkedOutFirst = {
    checked_out: 0,
    available: 1,
    unavailable: 2,
    not_held: 3,
    unknown: 4,
  };
  const unavailableFirst = {
    unavailable: 0,
    available: 1,
    checked_out: 2,
    not_held: 3,
    unknown: 4,
  };
  const order = {
    "available-first": availableFirst,
    "checked-out-first": checkedOutFirst,
    "unavailable-first": unavailableFirst,
  }[state.availabilitySort];
  return [...items].sort(
    (left, right) =>
      (order[left.availability_status] ?? 4) -
        (order[right.availability_status] ?? 4) ||
      left.id - right.id,
  );
};

const renderStats = () => {
  const categories = new Set(state.items.map((item) => item.category).filter(Boolean));
  document.querySelector("#total-stat").textContent = state.items.length;
  document.querySelector("#kit-stat").textContent = state.items.filter(
    (item) => item.components.length,
  ).length;
  document.querySelector("#category-stat").textContent = categories.size;
};

const renderFilters = () => {
  const categories = [...new Set(state.items.map((item) => item.category).filter(Boolean))].sort();
  filters.innerHTML = [
    `<button class="filter-chip ${state.category ? "" : "active"}" type="button" data-category="">All items</button>`,
    ...categories.map(
      (category) =>
        `<button class="filter-chip ${state.category === category ? "active" : ""}" type="button" data-category="${escapeHtml(category)}">${escapeHtml(category)}</button>`,
    ),
  ].join("");
};

const renderAvailabilityControls = () => {
  const definitions = [
    ["", "All statuses"],
    ["available", "Available"],
    ["checked_out", "Checked out"],
    ["unavailable", "Unavailable"],
    ["not_held", "Not held"],
    ["unknown", "Unknown"],
  ];
  availabilityFilters.innerHTML = definitions
    .map(([status, label]) => {
      const count = status
        ? state.items.filter((item) => item.availability_status === status).length
        : state.items.length;
      return `
        <button
          class="availability-filter ${state.availabilityFilter === status ? "active" : ""}"
          type="button"
          data-availability-filter="${status}"
        >
          ${status ? "<i aria-hidden=\"true\"></i>" : ""}
          ${escapeHtml(label)} <span>${count}</span>
        </button>`;
    })
    .join("");
  availabilitySort.value = state.availabilitySort;
};

const renderItems = () => {
  const items = visibleItems();
  if (!items.length) {
    const hasFilters = Boolean(
      state.query || state.category || state.availabilityFilter
    );
    grid.innerHTML = `
      <div class="empty-state">
        <span class="empty-icon" aria-hidden="true">${hasFilters ? "⌕" : "＋"}</span>
        <h3>${hasFilters ? "Nothing on this shelf" : "Your shelves are ready"}</h3>
        <p>${
          hasFilters
            ? "Try a different search or category to find what you’re looking for."
            : isAdmin()
              ? "Add your first lendable item and begin building a collection your community can share."
              : "There are no inventory items to display yet."
        }</p>
        ${
          hasFilters
            ? `<button class="secondary-button" id="clear-filters" type="button">Clear filters</button>`
            : isAdmin()
              ? `<button class="primary-button" id="empty-add-item" type="button">＋ Add your first item</button>`
              : ""
        }
      </div>`;
    return;
  }

  grid.innerHTML = items
    .map((item) => {
      const imageUrl = safeUrl(item.image_url);
      const availability = availabilityInfo(item);
      const componentLabel =
        item.components.length === 1 ? "1 part" : `${item.components.length} parts`;
      return `
        <article class="item-card">
          <div class="item-image">
            ${
              imageUrl
                ? `<img src="${escapeHtml(imageUrl)}" alt="" loading="lazy" />`
                : `<span class="item-placeholder" aria-hidden="true">${escapeHtml(itemInitials(item.name))}</span>`
            }
            <span class="category-badge">${escapeHtml(item.category || "Uncategorized")}</span>
            ${
              item.library_url
                ? `<span class="availability-badge ${availability.status}"><i></i>${escapeHtml(availability.shortLabel)}</span>`
                : ""
            }
          </div>
          <div class="item-card-body">
            <h3>${escapeHtml(item.name)}</h3>
            <p>${escapeHtml(item.description || "No description has been added yet.")}</p>
            <div class="item-meta">
              <span class="barcode">${escapeHtml(item.barcode)}</span>
              <span class="parts-count">${componentLabel}</span>
            </div>
          </div>
          <button class="card-open" type="button" data-item-id="${item.id}" aria-label="View ${escapeHtml(item.name)}"></button>
        </article>`;
    })
    .join("");
};

const renderAll = () => {
  renderStats();
  renderFilters();
  renderAvailabilityControls();
  renderItems();
};

const replaceItem = (item) => {
  const index = state.items.findIndex((candidate) => candidate.id === item.id);
  if (index >= 0) state.items[index] = item;
};

const refreshAvailabilityForItem = (item, { showErrors = false } = {}) => {
  if (!item.library_url) return Promise.resolve(item);
  const existing = state.refreshPromises.get(item.id);
  if (existing) return existing;

  state.refreshingIds.add(item.id);
  renderAvailabilityControls();
  renderItems();

  const refreshPromise = request(
    `/lendery/items/${item.id}/availability/refresh`,
    { method: "POST" },
  )
    .then((refreshedItem) => {
      replaceItem(refreshedItem);
      if (showErrors && refreshedItem.availability_error) {
        showToast("The catalogue could not be checked.");
      }
      return refreshedItem;
    })
    .catch((error) => {
      if (showErrors) showToast(error.message);
      return {
        ...item,
        availability_error: item.availability_error || error.message,
      };
    })
    .finally(() => {
      state.refreshingIds.delete(item.id);
      state.refreshPromises.delete(item.id);
      renderAll();
    });

  state.refreshPromises.set(item.id, refreshPromise);
  return refreshPromise;
};

const availabilityIsStale = (item) => {
  if (!item.library_url || !item.availability_checked_at) {
    return Boolean(item.library_url);
  }
  if (
    (item.availability_status_version ?? 1) <
    AVAILABILITY_STATUS_VERSION
  ) {
    return true;
  }
  const checkedAt = new Date(item.availability_checked_at).getTime();
  return (
    Number.isNaN(checkedAt) ||
    Date.now() - checkedAt >= AVAILABILITY_STALE_MS
  );
};

const refreshStaleAvailability = async () => {
  const queue = state.items.filter(availabilityIsStale);
  if (!queue.length) return;

  const worker = async () => {
    while (queue.length) {
      const item = queue.shift();
      await refreshAvailabilityForItem(item);
    }
  };
  await Promise.all(
    Array.from(
      { length: Math.min(AUTO_REFRESH_CONCURRENCY, queue.length) },
      worker,
    ),
  );
};

const loadItems = async () => {
  try {
    state.items = await request("/lendery/items?limit=100");
    renderAll();
    refreshStaleAvailability();
  } catch (error) {
    grid.innerHTML = `
      <div class="error-state">
        <span class="empty-icon" aria-hidden="true">!</span>
        <h3>We couldn’t reach the shelves</h3>
        <p>${escapeHtml(error.message)} Please try again.</p>
        <button class="secondary-button" id="retry-load" type="button">Try again</button>
      </div>`;
  }
};

const openItemDialog = (item = null) => {
  itemForm.reset();
  formError.textContent = "";
  document.querySelector("#item-id").value = item?.id || "";
  document.querySelector("#dialog-title").textContent = item ? "Edit item" : "Add a new item";
  document.querySelector("#save-item").textContent = item ? "Save changes" : "Save item";

  if (item) {
    for (const field of [
      "name",
      "barcode",
      "category",
      "description",
      "purchase_price",
      "image_url",
      "manual_url",
      "purchase_url",
      "library_url",
      "notes",
    ]) {
      itemForm.elements[field].value = item[field] ?? "";
    }
  }
  dialog.showModal();
  window.setTimeout(() => itemForm.elements.name.focus(), 50);
};

const formPayload = () => {
  const data = new FormData(itemForm);
  const payload = {};
  for (const [key, value] of data.entries()) {
    if (key === "id") continue;
    const trimmed = typeof value === "string" ? value.trim() : value;
    payload[key] = trimmed || null;
  }
  payload.name = String(data.get("name")).trim();
  payload.barcode = String(data.get("barcode")).trim();
  if (payload.purchase_price) payload.purchase_price = Number(payload.purchase_price);
  return payload;
};

const closeDrawer = () => {
  drawer.classList.remove("open");
  drawer.setAttribute("aria-hidden", "true");
  drawerBackdrop.classList.remove("open");
  window.setTimeout(() => {
    drawerBackdrop.hidden = true;
  }, 220);
  state.selectedId = null;
  state.checkedComponents.clear();
};

const renderDrawer = (item) => {
  const imageUrl = safeUrl(item.image_url);
  const manualUrl = safeUrl(item.manual_url);
  const purchaseUrl = safeUrl(item.purchase_url);
  const libraryUrl = safeUrl(item.library_url);
  const availability = availabilityInfo(item);
  const components = item.components || [];
  const checkedCount = components.filter((component) =>
    state.checkedComponents.has(component.id),
  ).length;
  const checklistPercent = components.length
    ? Math.round((checkedCount / components.length) * 100)
    : 0;

  drawerContent.innerHTML = `
    <div class="drawer-hero">
      ${
        imageUrl
          ? `<img src="${escapeHtml(imageUrl)}" alt="" />`
          : `<span class="item-placeholder" aria-hidden="true">${escapeHtml(itemInitials(item.name))}</span>`
      }
      <button class="icon-button drawer-close" id="drawer-close" type="button" aria-label="Close item details">×</button>
    </div>
    <div class="drawer-body">
      <p class="drawer-category">${escapeHtml(item.category || "Uncategorized")}</p>
      <div class="drawer-title-row">
        <h2 id="drawer-title">${escapeHtml(item.name)}</h2>
        ${item.purchase_price ? `<span class="drawer-price">$${Number(item.purchase_price).toFixed(2)}</span>` : ""}
      </div>
      <p class="drawer-description">${escapeHtml(item.description || "No description has been added yet.")}</p>

      <section class="availability-panel ${availability.status}" aria-label="Pierre Berton availability">
        <div class="availability-heading">
          <div>
            <p class="drawer-category">Pierre Berton Resource Library</p>
            <h3><i aria-hidden="true"></i>${escapeHtml(availability.label)}</h3>
          </div>
          ${
            libraryUrl
              ? `<button id="refresh-availability" type="button">Refresh</button>`
              : ""
          }
        </div>
        <p>${escapeHtml(availability.description)}</p>
        <div class="availability-footer">
          <span>${escapeHtml(formatCheckedAt(item.availability_checked_at))}</span>
          ${
            libraryUrl
              ? `<a href="${escapeHtml(libraryUrl)}" target="_blank" rel="noreferrer">Open catalogue ↗</a>`
              : ""
          }
        </div>
        ${
          item.availability_error
            ? `<small>Latest check failed; the last known status is shown.</small>`
            : ""
        }
      </section>

      <dl class="detail-list">
        <div><dt>Barcode</dt><dd>${escapeHtml(item.barcode)}</dd></div>
        <div><dt>Record</dt><dd>#${item.id}</dd></div>
        <div><dt>Manual</dt><dd>${manualUrl ? `<a href="${escapeHtml(manualUrl)}" target="_blank" rel="noreferrer">Open manual ↗</a>` : "Not added"}</dd></div>
        <div><dt>Purchase info</dt><dd>${purchaseUrl ? `<a href="${escapeHtml(purchaseUrl)}" target="_blank" rel="noreferrer">Open source ↗</a>` : "Not added"}</dd></div>
      </dl>

      ${item.notes ? `<p class="drawer-description"><strong>Staff notes:</strong> ${escapeHtml(item.notes)}</p>` : ""}

      <section class="components-section">
        <div class="section-title-row">
          <div>
            <p class="drawer-category">Return checklist</p>
            <h3>Check every piece</h3>
          </div>
          ${
            components.length
              ? `<button class="reset-checklist" id="reset-checklist" type="button">Reset</button>`
              : ""
          }
        </div>
        ${
          components.length
            ? `<div class="checklist-status">
                <div>
                  <strong id="checklist-count">${checkedCount} of ${components.length} checked</strong>
                  <span id="checklist-message">${checkedCount === components.length ? "Kit complete and ready to return" : "Tap each part as you find it"}</span>
                </div>
                <b id="checklist-percent">${checklistPercent}%</b>
              </div>
              <div class="checklist-track"><span id="checklist-bar" style="width: ${checklistPercent}%"></span></div>`
            : ""
        }
        <div class="component-list">
          ${
            components.length
              ? components
                  .map((component) => {
                    const componentImage = safeUrl(component.image_url);
                    const isChecked = state.checkedComponents.has(component.id);
                    return `
                      <article class="component-card ${isChecked ? "checked" : ""}" data-component-card="${component.id}">
                        <label class="component-visual">
                          <input
                            type="checkbox"
                            data-check-component="${component.id}"
                            ${isChecked ? "checked" : ""}
                            aria-label="Mark ${escapeHtml(component.name)} as present"
                          />
                          ${
                            componentImage
                              ? `<img src="${escapeHtml(componentImage)}" alt="${escapeHtml(component.name)}" loading="lazy" />`
                              : `<span class="component-placeholder" aria-hidden="true">${escapeHtml(itemInitials(component.name))}</span>`
                          }
                          <span class="component-check" aria-hidden="true">✓</span>
                        </label>
                        <div class="component-info">
                          <div>
                            <strong>${escapeHtml(component.name)}</strong>
                            <small>Quantity: ${component.quantity}${component.optional ? " · Optional" : ""}</small>
                          </div>
                          ${
                            isAdmin()
                              ? `<button class="remove-component" type="button" data-component-id="${component.id}" aria-label="Remove ${escapeHtml(component.name)}">×</button>`
                              : ""
                          }
                          ${component.check_in_notes ? `<p>${escapeHtml(component.check_in_notes)}</p>` : ""}
                        </div>
                      </article>`;
                  })
                  .join("")
              : `<div class="component-empty">No components yet. Add the parts staff should check at return.</div>`
          }
        </div>
        ${
          isAdmin()
            ? `<form class="component-form" id="component-form">
          <p>Add a checklist component</p>
          <div class="component-form-grid">
            <input name="name" required maxlength="200" placeholder="Component name" aria-label="Component name" />
            <input name="quantity" required type="number" min="1" value="1" aria-label="Quantity" />
            <input class="component-url-input" name="image_url" type="url" placeholder="Image URL (recommended)" aria-label="Component image URL" />
            <input class="component-note-input" name="check_in_notes" maxlength="500" placeholder="Return note, e.g. check for charger" aria-label="Check-in note" />
            <label class="optional-check"><input name="optional" type="checkbox" /> Optional part</label>
            <button type="submit">＋ Add part</button>
          </div>
        </form>`
            : ""
        }
      </section>

      ${
        isAdmin()
          ? `<div class="drawer-actions">
        <button class="delete-item" id="delete-item" type="button">Delete item</button>
        <button class="edit-item" id="edit-item" type="button">Edit item</button>
      </div>`
          : ""
      }
    </div>`;
};

const openDrawer = async (itemId) => {
  const item = state.items.find((candidate) => candidate.id === Number(itemId));
  if (!item) return;
  state.selectedId = item.id;
  state.checkedComponents.clear();
  renderDrawer(item);
  drawerBackdrop.hidden = false;
  requestAnimationFrame(() => drawerBackdrop.classList.add("open"));
  drawer.classList.add("open");
  drawer.setAttribute("aria-hidden", "false");
  document.querySelector("#drawer-close").focus();

  if (!item.library_url) return;
  const refreshedItem = await refreshAvailabilityForItem(item, {
    showErrors: true,
  });
  if (state.selectedId === item.id) renderDrawer(refreshedItem);
};

const refreshSelectedItem = async () => {
  if (!state.selectedId) return;
  const item = await request(`/lendery/items/${state.selectedId}`);
  const index = state.items.findIndex((candidate) => candidate.id === item.id);
  if (index >= 0) state.items[index] = item;
  renderAll();
  renderDrawer(item);
};

itemForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!isAdmin()) return;
  formError.textContent = "";
  const saveButton = document.querySelector("#save-item");
  saveButton.disabled = true;
  const id = document.querySelector("#item-id").value;

  try {
    const payload = formPayload();
    const item = await request(id ? `/lendery/items/${id}` : "/lendery/items", {
      method: id ? "PATCH" : "POST",
      body: JSON.stringify(payload),
    });

    const existingIndex = state.items.findIndex((candidate) => candidate.id === item.id);
    if (existingIndex >= 0) state.items[existingIndex] = item;
    else state.items.push(item);
    dialog.close();
    renderAll();
    if (state.selectedId === item.id) renderDrawer(item);
    showToast(id ? "Item updated." : "Item added to the collection.");
    if (availabilityIsStale(item)) refreshAvailabilityForItem(item);
  } catch (error) {
    formError.textContent = error.message;
  } finally {
    saveButton.disabled = false;
  }
});

document.addEventListener("click", async (event) => {
  const addTrigger = event.target.closest(
    "#nav-add-item, #header-add-item, #panel-add-item, #empty-add-item",
  );
  if (addTrigger) {
    if (!isAdmin()) return;
    openItemDialog();
    return;
  }

  if (event.target.closest("[data-close-dialog]")) {
    dialog.close();
    return;
  }

  const itemTrigger = event.target.closest("[data-item-id]");
  if (itemTrigger) {
    openDrawer(itemTrigger.dataset.itemId);
    return;
  }

  if (event.target.closest("#drawer-close") || event.target === drawerBackdrop) {
    closeDrawer();
    return;
  }

  if (event.target.closest("#clear-filters")) {
    state.query = "";
    state.category = "";
    state.availabilityFilter = "";
    state.availabilitySort = "";
    searchInput.value = "";
    renderFilters();
    renderAvailabilityControls();
    renderItems();
    return;
  }

  if (event.target.closest("#retry-load")) {
    grid.innerHTML = `<div class="loading-state"><span class="loading-mark"></span><p>Checking the shelves…</p></div>`;
    loadItems();
    return;
  }

  const filter = event.target.closest("[data-category]");
  if (filter) {
    state.category = filter.dataset.category;
    renderFilters();
    renderItems();
    return;
  }

  const availabilityFilter = event.target.closest("[data-availability-filter]");
  if (availabilityFilter) {
    state.availabilityFilter = availabilityFilter.dataset.availabilityFilter;
    renderAvailabilityControls();
    renderItems();
    return;
  }

  if (event.target.closest("#edit-item")) {
    if (!isAdmin()) return;
    const item = state.items.find((candidate) => candidate.id === state.selectedId);
    if (item) openItemDialog(item);
    return;
  }

  if (event.target.closest("#refresh-availability")) {
    const button = event.target.closest("#refresh-availability");
    button.disabled = true;
    const currentItem = state.items.find(
      (candidate) => candidate.id === state.selectedId,
    );
    if (!currentItem) return;
    const item = await refreshAvailabilityForItem(currentItem, {
      showErrors: true,
    });
    if (state.selectedId === item.id) renderDrawer(item);
    if (!item.availability_error) showToast("Availability refreshed.");
    return;
  }

  if (event.target.closest("#reset-checklist")) {
    state.checkedComponents.clear();
    const item = state.items.find((candidate) => candidate.id === state.selectedId);
    if (item) renderDrawer(item);
    return;
  }

  if (event.target.closest("#delete-item")) {
    if (!isAdmin()) return;
    const item = state.items.find((candidate) => candidate.id === state.selectedId);
    if (!item || !window.confirm(`Delete “${item.name}”? This cannot be undone.`)) return;
    try {
      await request(`/lendery/items/${item.id}`, { method: "DELETE" });
      state.items = state.items.filter((candidate) => candidate.id !== item.id);
      closeDrawer();
      renderAll();
      showToast("Item deleted.");
    } catch (error) {
      showToast(error.message);
    }
    return;
  }

  const removeComponent = event.target.closest("[data-component-id]");
  if (removeComponent) {
    if (!isAdmin()) return;
    try {
      await request(`/lendery/components/${removeComponent.dataset.componentId}`, {
        method: "DELETE",
      });
      await refreshSelectedItem();
      showToast("Component removed.");
    } catch (error) {
      showToast(error.message);
    }
  }
});

drawerContent.addEventListener("submit", async (event) => {
  if (event.target.id !== "component-form") return;
  event.preventDefault();
  if (!isAdmin()) return;
  const data = new FormData(event.target);
  try {
    await request(`/lendery/items/${state.selectedId}/components`, {
      method: "POST",
      body: JSON.stringify({
        name: String(data.get("name")).trim(),
        quantity: Number(data.get("quantity")),
        image_url: String(data.get("image_url")).trim() || null,
        check_in_notes: String(data.get("check_in_notes")).trim() || null,
        optional: data.get("optional") === "on",
      }),
    });
    await refreshSelectedItem();
    showToast("Component added.");
  } catch (error) {
    showToast(error.message);
  }
});

drawerContent.addEventListener("change", (event) => {
  const checkbox = event.target.closest("[data-check-component]");
  if (!checkbox) return;
  const componentId = Number(checkbox.dataset.checkComponent);
  if (checkbox.checked) state.checkedComponents.add(componentId);
  else state.checkedComponents.delete(componentId);

  const item = state.items.find((candidate) => candidate.id === state.selectedId);
  if (!item) return;
  const checkedCount = item.components.filter((component) =>
    state.checkedComponents.has(component.id),
  ).length;
  const percent = item.components.length
    ? Math.round((checkedCount / item.components.length) * 100)
    : 0;
  const card = drawerContent.querySelector(`[data-component-card="${componentId}"]`);
  card?.classList.toggle("checked", checkbox.checked);
  document.querySelector("#checklist-count").textContent =
    `${checkedCount} of ${item.components.length} checked`;
  document.querySelector("#checklist-message").textContent =
    checkedCount === item.components.length
      ? "Kit complete and ready to return"
      : "Tap each part as you find it";
  document.querySelector("#checklist-percent").textContent = `${percent}%`;
  document.querySelector("#checklist-bar").style.width = `${percent}%`;
});

searchInput.addEventListener("input", (event) => {
  state.query = event.target.value;
  renderItems();
});

availabilitySort.addEventListener("change", (event) => {
  state.availabilitySort = event.target.value;
  renderItems();
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && drawer.classList.contains("open")) closeDrawer();
});

loginDialog.addEventListener("cancel", (event) => event.preventDefault());

loginForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  loginError.textContent = "";
  const button = event.target.querySelector("button[type='submit']");
  const data = new FormData(event.target);
  button.disabled = true;
  try {
    const user = await request("/lendery/auth/login", {
      method: "POST",
      body: JSON.stringify({
        username: String(data.get("username")).trim(),
        password: String(data.get("password")),
      }),
    });
    applyUser(user);
    event.target.reset();
    loginDialog.close();
    await loadItems();
  } catch (error) {
    loginError.textContent = error.message;
  } finally {
    button.disabled = false;
  }
});

document.querySelector("#logout-button").addEventListener("click", async () => {
  try {
    await request("/lendery/auth/logout", { method: "POST" });
  } finally {
    state.items = [];
    showLogin();
    renderAll();
  }
});

document.querySelector("#change-passwords").addEventListener("click", () => {
  if (!isAdmin()) return;
  passwordForm.reset();
  passwordError.textContent = "";
  passwordDialog.showModal();
});

document.querySelectorAll("[data-close-password-dialog]").forEach((button) => {
  button.addEventListener("click", () => passwordDialog.close());
});

passwordForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  passwordError.textContent = "";
  const data = new FormData(event.target);
  const newPassword = String(data.get("new_password"));
  if (newPassword !== String(data.get("confirm_password"))) {
    passwordError.textContent = "The passwords do not match.";
    return;
  }
  const button = event.target.querySelector("button[type='submit']");
  button.disabled = true;
  try {
    await request("/lendery/auth/password", {
      method: "PUT",
      body: JSON.stringify({
        username: String(data.get("username")),
        new_password: newPassword,
      }),
    });
    passwordDialog.close();
    showToast("Password updated.");
  } catch (error) {
    passwordError.textContent = error.message;
  } finally {
    button.disabled = false;
  }
});

const initialize = async () => {
  try {
    const user = await request("/lendery/auth/me");
    applyUser(user);
    await loadItems();
  } catch (error) {
    if (error.status !== 401) {
      showToast(error.message);
    }
    showLogin();
  }
};

initialize();
