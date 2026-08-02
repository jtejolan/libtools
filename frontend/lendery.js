const state = {
  user: null,
  items: [],
  query: "",
  category: "",
  availabilityFilter: "",
  availabilitySort: "",
  selectedId: null,
  checkedComponents: new Set(),
  maintenanceByItem: new Map(),
  refreshingIds: new Set(),
  refreshPromises: new Map(),
  maintenanceQueue: [],
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
const accountActions = document.querySelector("#account-actions");
const roleBadge = document.querySelector("#role-badge");
const accountMenu = document.querySelector("#account-menu");
const accountMenuName = document.querySelector("#account-menu-name");
const maintenanceDialog = document.querySelector("#maintenance-dialog");
const maintenanceCaseForm = document.querySelector("#maintenance-case-form");
const maintenanceFormError = document.querySelector("#maintenance-form-error");
const needsAttentionCountBadge = document.querySelector("#needs-attention-count");
const needsAttentionDialog = document.querySelector("#needs-attention-dialog");
const needsAttentionContent = document.querySelector("#needs-attention-content");

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
  const hasJsonBody = options.body && !(options.body instanceof FormData);
  const response = await fetch(url, {
    ...options,
    headers: {
      ...(hasJsonBody ? { "Content-Type": "application/json" } : {}),
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

const uploadComponentPhoto = async (componentId, file) => {
  if (file.size > 10 * 1024 * 1024) {
    throw new Error("The photo must be 10 MB or smaller.");
  }
  const body = new FormData();
  body.append("image", file);
  return request(`/lendery/components/${componentId}/image`, {
    method: "POST",
    body,
  });
};

const canManage = () =>
  state.user?.role === "admin" || state.user?.tools?.includes("lendery_manage");

const applyUser = (user) => {
  state.user = user;
  accountActions.hidden = false;
  roleBadge.textContent = canManage() ? "Lendery editor" : "Lendery viewer";
  accountMenuName.textContent = user.username;
  document.querySelectorAll("[data-admin-only]").forEach((element) => {
    element.hidden = !canManage();
  });
  document.querySelectorAll("[data-platform-admin-only]").forEach((element) => {
    element.hidden = user.role !== "admin";
  });
};

const showLogin = () => {
  state.user = null;
  state.maintenanceByItem.clear();
  state.maintenanceQueue = [];
  accountActions.hidden = true;
  accountMenu.open = false;
  closeDrawer();
  if (dialog.open) dialog.close();
  if (maintenanceDialog.open) maintenanceDialog.close();
  if (needsAttentionDialog.open) needsAttentionDialog.close();
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

const formatMaintenanceDate = (value) => {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "Date unavailable" : date.toLocaleString();
};

const maintenanceStatusLabel = (status) =>
  ({
    open: "Open",
    waiting_for_part: "Waiting for part",
    in_repair: "In repair",
    resolved: "Resolved",
    cancelled: "Cancelled",
  })[status] || status;

const maintenanceEventLabel = (type) =>
  ({
    issue_update: "Update",
    part_ordered: "Part ordered",
    part_received: "Part received",
    part_installed: "Part installed",
    repair_completed: "Repair completed",
  })[type] || type;

const renderMaintenanceEvent = (entry) => {
  const details = [];
  if (entry.part_name) {
    details.push(`${entry.quantity || 1} × ${entry.part_name}`);
  }
  if (entry.cost !== null && entry.cost !== undefined) {
    details.push(`$${Number(entry.cost).toFixed(2)}`);
  }
  if (entry.order_number) details.push(`Order ${entry.order_number}`);
  const vendorUrl = safeUrl(entry.vendor_url);
  return `<li class="maintenance-event">
    <span class="maintenance-event-mark" aria-hidden="true"></span>
    <div>
      <div class="maintenance-event-heading">
        <strong>${escapeHtml(maintenanceEventLabel(entry.event_type))}</strong>
        <time>${escapeHtml(formatMaintenanceDate(entry.created_at))}</time>
      </div>
      ${entry.note ? `<p>${escapeHtml(entry.note)}</p>` : ""}
      ${details.length ? `<small>${escapeHtml(details.join(" · "))}</small>` : ""}
      ${vendorUrl ? `<a href="${escapeHtml(vendorUrl)}" target="_blank" rel="noreferrer">Open order source ↗</a>` : ""}
      <small>Recorded by ${escapeHtml(entry.created_by_name)}${entry.status_after ? ` · ${escapeHtml(maintenanceStatusLabel(entry.status_after))}` : ""}</small>
    </div>
  </li>`;
};

const renderMaintenanceSection = (cases) => `
  <section class="maintenance-section">
    <div class="section-title-row">
      <div>
        <p class="drawer-category">Editor workspace</p>
        <h3>Maintenance &amp; repairs</h3>
      </div>
      <button class="maintenance-new" id="new-maintenance-case" type="button">＋ Report issue</button>
    </div>
    <p class="maintenance-intro">Record problems, replacement orders, installations, and completed repairs.</p>
    <div class="maintenance-cases">
      ${
        cases.length
          ? cases
              .map(
                (repairCase) => `<article class="maintenance-case ${escapeHtml(repairCase.status)}">
                  <div class="maintenance-case-heading">
                    <div>
                      <span class="maintenance-status">${escapeHtml(maintenanceStatusLabel(repairCase.status))}</span>
                      <h4>${escapeHtml(repairCase.title)}</h4>
                    </div>
                    ${repairCase.component_name ? `<small>${escapeHtml(repairCase.component_name)}</small>` : ""}
                  </div>
                  ${repairCase.description ? `<p>${escapeHtml(repairCase.description)}</p>` : ""}
                  <small>Opened ${escapeHtml(formatMaintenanceDate(repairCase.opened_at))} by ${escapeHtml(repairCase.opened_by_name)}</small>
                  ${
                    repairCase.events.length
                      ? `<ol class="maintenance-timeline">${repairCase.events.map(renderMaintenanceEvent).join("")}</ol>`
                      : `<p class="maintenance-empty">No updates recorded yet.</p>`
                  }
                  <form class="maintenance-update-form" data-maintenance-case-id="${repairCase.id}">
                    <div class="maintenance-update-grid">
                      <label class="field">
                        <span>Update type</span>
                        <select name="event_type">
                          <option value="issue_update">General update</option>
                          <option value="part_ordered">Part ordered</option>
                          <option value="part_received">Part received</option>
                          <option value="part_installed">Part installed</option>
                          <option value="repair_completed">Repair completed</option>
                        </select>
                      </label>
                      <label class="field">
                        <span>New status</span>
                        <select name="new_status">
                          <option value="">Update automatically</option>
                          <option value="open">Open</option>
                          <option value="waiting_for_part">Waiting for part</option>
                          <option value="in_repair">In repair</option>
                          <option value="resolved">Resolved</option>
                          <option value="cancelled">Cancelled</option>
                        </select>
                      </label>
                    </div>
                    <label class="field">
                      <span>Note</span>
                      <textarea name="note" rows="2" placeholder="What changed?"></textarea>
                    </label>
                    <details class="maintenance-part-details">
                      <summary>Part or order details</summary>
                      <div class="maintenance-update-grid">
                        <label class="field"><span>Part name</span><input name="part_name" maxlength="200" /></label>
                        <label class="field"><span>Quantity</span><input name="quantity" type="number" min="1" /></label>
                        <label class="field"><span>Cost</span><input name="cost" type="number" min="0" step="0.01" /></label>
                        <label class="field"><span>Order number</span><input name="order_number" maxlength="100" /></label>
                        <label class="field maintenance-order-url"><span>Vendor or order URL</span><input name="vendor_url" type="url" placeholder="https://…" /></label>
                      </div>
                    </details>
                    <button type="submit">Add to repair log</button>
                  </form>
                </article>`,
              )
              .join("")
          : `<div class="maintenance-empty-state"><strong>No repair history</strong><span>Report an issue when this item needs attention.</span></div>`
      }
    </div>
  </section>`;

const unresolvedUnavailableItems = () => {
  const flagged = new Set(state.maintenanceQueue.map((entry) => entry.item_id));
  return state.items.filter(
    (item) => item.availability_status === "unavailable" && !flagged.has(item.id),
  );
};

const needsAttentionCount = () =>
  state.maintenanceQueue.length + unresolvedUnavailableItems().length;

const renderNeedsAttentionButton = () => {
  const count = needsAttentionCount();
  needsAttentionCountBadge.textContent = String(count);
  needsAttentionCountBadge.hidden = count === 0;
};

const renderNeedsAttentionDialog = () => {
  const cases = state.maintenanceQueue;
  const flagged = unresolvedUnavailableItems();

  const caseRows = cases
    .map(
      (entry) => `
        <button class="needs-attention-row ${escapeHtml(entry.status)}" type="button" data-open-item="${entry.item_id}">
          <div class="needs-attention-row-heading">
            <div>
              <span class="maintenance-status">${escapeHtml(maintenanceStatusLabel(entry.status))}</span>
              <h4>${escapeHtml(entry.title)}</h4>
            </div>
          </div>
          <small>${escapeHtml(entry.item_name)} · ${escapeHtml(entry.item_barcode)}${entry.component_name ? ` · ${escapeHtml(entry.component_name)}` : ""}</small><br />
          <small>Opened ${escapeHtml(formatMaintenanceDate(entry.opened_at))} by ${escapeHtml(entry.opened_by_name)}</small>
        </button>`,
    )
    .join("");

  const flaggedRows = flagged
    .map(
      (item) => `
        <div class="needs-attention-row unavailable-flag">
          <div>
            <span class="maintenance-status">Unavailable</span>
            <h4>${escapeHtml(item.name)}</h4>
            <small>${escapeHtml(item.barcode)}</small>
          </div>
          <button class="needs-attention-log-issue" type="button" data-log-issue="${item.id}">Log an issue</button>
        </div>`,
    )
    .join("");

  needsAttentionContent.innerHTML = `
    ${
      cases.length
        ? `<div class="needs-attention-group">
            <h3>Open maintenance cases</h3>
            <div class="needs-attention-list">${caseRows}</div>
          </div>`
        : ""
    }
    ${
      flagged.length
        ? `<div class="needs-attention-group">
            <h3>Unavailable, no issue logged</h3>
            <div class="needs-attention-list">${flaggedRows}</div>
          </div>`
        : ""
    }
    ${
      !cases.length && !flagged.length
        ? `<div class="maintenance-empty-state"><strong>All clear</strong><span>No open issues or unresolved availability problems.</span></div>`
        : ""
    }
  `;
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
  };
  const checkedOutFirst = {
    checked_out: 0,
    available: 1,
    unavailable: 2,
  };
  const unavailableFirst = {
    unavailable: 0,
    available: 1,
    checked_out: 2,
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
            : canManage()
              ? "Add your first lendable item and begin building a collection your community can share."
              : "There are no inventory items to display yet."
        }</p>
        ${
          hasFilters
            ? `<button class="secondary-button" id="clear-filters" type="button">Clear filters</button>`
            : canManage()
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

const loadMaintenanceQueue = async () => {
  if (!canManage()) return;
  try {
    state.maintenanceQueue = await request("/lendery/maintenance");
  } catch (error) {
    state.maintenanceQueue = [];
  }
  renderNeedsAttentionButton();
};

const loadItems = async () => {
  try {
    state.items = await request("/lendery/items?limit=100");
    renderAll();
    refreshStaleAvailability();
    loadMaintenanceQueue();
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
  const importStatus = document.querySelector("#import-item-status");
  importStatus.textContent =
    "Paste a Lendery catalogue record to fill the item details automatically.";
  importStatus.className = "field-help";
  document.querySelector("#import-lendery-item").disabled = false;
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
  window.setTimeout(
    () => (item ? itemForm.elements.name : itemForm.elements.library_url).focus(),
    50,
  );
};

const importLenderyItem = async () => {
  const button = document.querySelector("#import-lendery-item");
  const status = document.querySelector("#import-item-status");
  const libraryUrl = itemForm.elements.library_url.value.trim();
  if (!libraryUrl) {
    status.textContent = "Paste a Vaughan Public Libraries Lendery link first.";
    status.className = "field-help error";
    itemForm.elements.library_url.focus();
    return;
  }

  button.disabled = true;
  button.textContent = "Finding details…";
  status.textContent = "Reading the catalogue record…";
  status.className = "field-help";
  try {
    const item = await request("/lendery/items/import", {
      method: "POST",
      body: JSON.stringify({ library_url: libraryUrl }),
    });
    ["name", "description", "image_url", "manual_url", "library_url"].forEach(
      (field) => {
        itemForm.elements[field].value = item[field] ?? "";
      },
    );
    status.textContent = "Details added. Add a barcode, review, then save.";
    status.className = "field-help success";
  } catch (error) {
    status.textContent = error.message;
    status.className = "field-help error";
  } finally {
    button.disabled = false;
    button.textContent = "Fill item details";
  }
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

      ${canManage() ? renderMaintenanceSection(state.maintenanceByItem.get(item.id) || []) : ""}

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
                            canManage()
                              ? `<button class="remove-component" type="button" data-component-id="${component.id}" aria-label="Remove ${escapeHtml(component.name)}">×</button>`
                              : ""
                          }
                          ${component.check_in_notes ? `<p>${escapeHtml(component.check_in_notes)}</p>` : ""}
                          ${
                            canManage()
                              ? `<div class="component-photo-actions">
                                  <label>
                                    <input type="file" accept="image/*,.heic,.heif" data-replace-component-photo="${component.id}" />
                                    ${componentImage ? "Replace photo" : "Add photo"}
                                  </label>
                                  ${componentImage ? `<button type="button" data-remove-component-photo="${component.id}">Remove photo</button>` : ""}
                                </div>`
                              : ""
                          }
                        </div>
                      </article>`;
                  })
                  .join("")
              : `<div class="component-empty">No components yet. Add the parts staff should check at return.</div>`
          }
        </div>
        ${
          canManage()
            ? `<form class="component-form" id="component-form">
          <p>Add a checklist component</p>
          <div class="component-form-grid">
            <input name="name" required maxlength="200" placeholder="Component name" aria-label="Component name" />
            <input name="quantity" required type="number" min="1" value="1" aria-label="Quantity" />
            <div class="component-photo-picker">
              <input id="component-photo-input" name="photo" type="file" accept="image/*,.heic,.heif" />
              <label for="component-photo-input">📷 Take or choose photo</label>
              <div class="component-photo-preview" id="component-photo-preview" hidden>
                <img alt="Selected component photo preview" />
                <button type="button" data-clear-component-photo aria-label="Remove selected photo">×</button>
              </div>
              <small>JPEG, PNG, WebP, or HEIC · up to 10 MB</small>
              <details>
                <summary>Use an image URL instead</summary>
                <input name="image_url" type="url" placeholder="https://…" aria-label="Component image URL" />
              </details>
            </div>
            <input class="component-note-input" name="check_in_notes" maxlength="500" placeholder="Return note, e.g. check for charger" aria-label="Check-in note" />
            <label class="optional-check"><input name="optional" type="checkbox" /> Optional part</label>
            <button type="submit">＋ Add part</button>
          </div>
        </form>`
            : ""
        }
      </section>

      ${
        canManage()
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

  if (canManage()) {
    try {
      const cases = await request(`/lendery/items/${item.id}/maintenance`);
      state.maintenanceByItem.set(item.id, cases);
      if (state.selectedId === item.id) renderDrawer(item);
    } catch (error) {
      showToast(error.message);
    }
  }

  if (!item.library_url) return;
  const refreshedItem = await refreshAvailabilityForItem(item, {
    showErrors: true,
  });
  if (state.selectedId === item.id) renderDrawer(refreshedItem);
};

const openMaintenanceDialog = () => {
  if (!canManage() || !state.selectedId) return;
  const item = state.items.find((candidate) => candidate.id === state.selectedId);
  if (!item) return;
  maintenanceCaseForm.reset();
  maintenanceFormError.textContent = "";
  const componentSelect = document.querySelector("#maintenance-component");
  componentSelect.innerHTML = `<option value="">Whole item</option>${item.components
    .map(
      (component) =>
        `<option value="${component.id}">${escapeHtml(component.name)}</option>`,
    )
    .join("")}`;
  maintenanceDialog.showModal();
};

const reloadMaintenance = async (itemId) => {
  const cases = await request(`/lendery/items/${itemId}/maintenance`);
  state.maintenanceByItem.set(itemId, cases);
  const item = state.items.find((candidate) => candidate.id === itemId);
  if (item && state.selectedId === itemId) renderDrawer(item);
  loadMaintenanceQueue();
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
  if (!canManage()) return;
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

maintenanceCaseForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!canManage() || !state.selectedId) return;
  const itemId = state.selectedId;
  maintenanceFormError.textContent = "";
  const button = event.target.querySelector("button[type='submit']");
  const data = new FormData(event.target);
  button.disabled = true;
  try {
    await request(`/lendery/items/${itemId}/maintenance`, {
      method: "POST",
      body: JSON.stringify({
        title: String(data.get("title")).trim(),
        description: String(data.get("description")).trim() || null,
        component_id: data.get("component_id")
          ? Number(data.get("component_id"))
          : null,
        status: data.get("status"),
      }),
    });
    await reloadMaintenance(itemId);
    maintenanceDialog.close();
    showToast("Repair log created.");
  } catch (error) {
    maintenanceFormError.textContent = error.message;
  } finally {
    button.disabled = false;
  }
});

document
  .querySelector("#import-lendery-item")
  .addEventListener("click", importLenderyItem);
itemForm.elements.library_url.addEventListener("keydown", (event) => {
  if (event.key !== "Enter") return;
  event.preventDefault();
  importLenderyItem();
});

document.addEventListener("click", async (event) => {
  const addTrigger = event.target.closest(
    "#nav-add-item, #header-add-item, #panel-add-item, #empty-add-item",
  );
  if (addTrigger) {
    if (!canManage()) return;
    openItemDialog();
    return;
  }

  if (event.target.closest("[data-close-dialog]")) {
    dialog.close();
    return;
  }

  if (event.target.closest("[data-close-maintenance-dialog]")) {
    maintenanceDialog.close();
    return;
  }

  if (event.target.closest("#needs-attention-button")) {
    if (!canManage()) return;
    await loadMaintenanceQueue();
    renderNeedsAttentionDialog();
    needsAttentionDialog.showModal();
    return;
  }

  if (event.target.closest("[data-close-needs-attention]")) {
    needsAttentionDialog.close();
    return;
  }

  const logIssueTrigger = event.target.closest("[data-log-issue]");
  if (logIssueTrigger) {
    needsAttentionDialog.close();
    await openDrawer(logIssueTrigger.dataset.logIssue);
    openMaintenanceDialog();
    return;
  }

  const needsAttentionItemTrigger = event.target.closest("[data-open-item]");
  if (needsAttentionItemTrigger) {
    needsAttentionDialog.close();
    openDrawer(needsAttentionItemTrigger.dataset.openItem);
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
    if (!canManage()) return;
    const item = state.items.find((candidate) => candidate.id === state.selectedId);
    if (item) openItemDialog(item);
    return;
  }

  if (event.target.closest("#new-maintenance-case")) {
    openMaintenanceDialog();
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
    if (!canManage()) return;
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
    if (!canManage()) return;
    try {
      await request(`/lendery/components/${removeComponent.dataset.componentId}`, {
        method: "DELETE",
      });
      await refreshSelectedItem();
      showToast("Component removed.");
    } catch (error) {
      showToast(error.message);
    }
    return;
  }

  const removePhoto = event.target.closest("[data-remove-component-photo]");
  if (removePhoto) {
    if (!canManage()) return;
    try {
      await request(
        `/lendery/components/${removePhoto.dataset.removeComponentPhoto}/image`,
        { method: "DELETE" },
      );
      await refreshSelectedItem();
      showToast("Component photo removed.");
    } catch (error) {
      showToast(error.message);
    }
    return;
  }

  if (event.target.closest("[data-clear-component-photo]")) {
    const input = drawerContent.querySelector("#component-photo-input");
    const preview = drawerContent.querySelector("#component-photo-preview");
    if (input) input.value = "";
    if (preview) {
      URL.revokeObjectURL(preview.dataset.objectUrl || "");
      preview.dataset.objectUrl = "";
      preview.hidden = true;
    }
  }
});

drawerContent.addEventListener("submit", async (event) => {
  const maintenanceForm = event.target.closest("[data-maintenance-case-id]");
  if (maintenanceForm) {
    event.preventDefault();
    if (!canManage() || !state.selectedId) return;
    const itemId = state.selectedId;
    const data = new FormData(maintenanceForm);
    const button = maintenanceForm.querySelector("button[type='submit']");
    button.disabled = true;
    try {
      await request(
        `/lendery/maintenance/${maintenanceForm.dataset.maintenanceCaseId}/events`,
        {
          method: "POST",
          body: JSON.stringify({
            event_type: data.get("event_type"),
            note: String(data.get("note")).trim() || null,
            part_name: String(data.get("part_name")).trim() || null,
            quantity: data.get("quantity") ? Number(data.get("quantity")) : null,
            cost: data.get("cost") ? Number(data.get("cost")) : null,
            vendor_url: String(data.get("vendor_url")).trim() || null,
            order_number: String(data.get("order_number")).trim() || null,
            new_status: data.get("new_status") || null,
          }),
        },
      );
      await reloadMaintenance(itemId);
      showToast("Repair log updated.");
    } catch (error) {
      button.disabled = false;
      showToast(error.message);
    }
    return;
  }

  if (event.target.id !== "component-form") return;
  event.preventDefault();
  if (!canManage()) return;
  const data = new FormData(event.target);
  try {
    const component = await request(`/lendery/items/${state.selectedId}/components`, {
      method: "POST",
      body: JSON.stringify({
        name: String(data.get("name")).trim(),
        quantity: Number(data.get("quantity")),
        image_url: String(data.get("image_url")).trim() || null,
        check_in_notes: String(data.get("check_in_notes")).trim() || null,
        optional: data.get("optional") === "on",
      }),
    });
    const photo = data.get("photo");
    if (photo instanceof File && photo.size) {
      try {
        await uploadComponentPhoto(component.id, photo);
      } catch (error) {
        await refreshSelectedItem();
        showToast(`Component added, but its photo was not uploaded: ${error.message}`);
        return;
      }
    }
    const preview = drawerContent.querySelector("#component-photo-preview");
    URL.revokeObjectURL(preview?.dataset.objectUrl || "");
    await refreshSelectedItem();
    showToast("Component added.");
  } catch (error) {
    showToast(error.message);
  }
});

drawerContent.addEventListener("change", async (event) => {
  const maintenanceType = event.target.closest(
    ".maintenance-update-form select[name='event_type']",
  );
  if (maintenanceType) {
    const form = maintenanceType.closest(".maintenance-update-form");
    const partDetails = form.querySelector(".maintenance-part-details");
    const partName = form.elements.part_name;
    const isPartEvent = maintenanceType.value.startsWith("part_");
    partDetails.open = isPartEvent;
    partName.required = isPartEvent;
    return;
  }

  const newPhoto = event.target.closest("#component-photo-input");
  if (newPhoto) {
    const preview = drawerContent.querySelector("#component-photo-preview");
    const file = newPhoto.files?.[0];
    if (!preview || !file) return;
    URL.revokeObjectURL(preview.dataset.objectUrl || "");
    preview.dataset.objectUrl = URL.createObjectURL(file);
    preview.querySelector("img").src = preview.dataset.objectUrl;
    preview.hidden = false;
    return;
  }

  const replacement = event.target.closest("[data-replace-component-photo]");
  if (replacement) {
    const file = replacement.files?.[0];
    if (!file || !canManage()) return;
    replacement.disabled = true;
    try {
      await uploadComponentPhoto(replacement.dataset.replaceComponentPhoto, file);
      await refreshSelectedItem();
      showToast("Component photo updated.");
    } catch (error) {
      replacement.disabled = false;
      replacement.value = "";
      showToast(error.message);
    }
    return;
  }

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

document.addEventListener("click", (event) => {
  if (accountMenu.open && !accountMenu.contains(event.target)) {
    accountMenu.open = false;
  }
});

document.addEventListener("keydown", (event) => {
  if (event.key !== "Escape") return;
  accountMenu.open = false;
  if (drawer.classList.contains("open")) closeDrawer();
});

loginDialog.addEventListener("cancel", (event) => event.preventDefault());

loginForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  loginError.textContent = "";
  const button = event.target.querySelector("button[type='submit']");
  const data = new FormData(event.target);
  button.disabled = true;
  try {
    const user = await request("/auth/login", {
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
    await request("/auth/logout", { method: "POST" });
  } finally {
    state.items = [];
    showLogin();
    renderAll();
  }
});

const initialize = async () => {
  try {
    const user = await request("/auth/me");
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
