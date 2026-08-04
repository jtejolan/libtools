const state = {
  options: null,
  type: "inventory",
};

const form = document.querySelector("#export-form");
const scopeSelect = document.querySelector("#export-scope");
const categoryField = document.querySelector("#category-field");
const categorySelect = document.querySelector("#export-category");
const itemField = document.querySelector("#item-field");
const itemSelect = document.querySelector("#export-item");
const includeRemovedRow = document.querySelector("#include-removed-row");
const includeRemoved = document.querySelector("#include-removed");
const historyNote = document.querySelector("#history-note");
const fieldGrid = document.querySelector("#field-grid");
const fieldCount = document.querySelector("#field-count");
const summaryTitle = document.querySelector("#summary-title");
const summaryScope = document.querySelector("#summary-scope");
const summaryFields = document.querySelector("#summary-fields");
const summaryHelp = document.querySelector("#summary-help");
const exportError = document.querySelector("#export-error");
const downloadButton = document.querySelector("#download-export");

const capitalizeFirst = (value = "") => {
  const characters = Array.from(String(value));
  return characters.length
    ? characters[0].toLocaleUpperCase() + characters.slice(1).join("")
    : "";
};

const requestJson = async (url, options = {}) => {
  const response = await fetch(url, options);
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const message = typeof body.detail === "string"
      ? body.detail
      : body.detail?.[0]?.msg || "Something went wrong.";
    const error = new Error(message);
    error.status = response.status;
    throw error;
  }
  return body;
};

const canManage = (user) =>
  user.role === "admin" || user.tools?.includes("lendery_manage");

const currentFields = () =>
  state.type === "inventory"
    ? state.options.inventory_fields
    : state.options.activity_fields;

const renderItemOptions = () => {
  const items = state.type === "activity"
    ? state.options.activity_items
    : state.options.items;
  const currentIds = new Set(state.options.items.map((item) => item.id));
  itemSelect.innerHTML = items.length
    ? items.map((item) => {
        const status = !currentIds.has(item.id)
          ? " (history only)"
          : item.lifecycle_status === "removed"
            ? " (removed)"
            : item.lifecycle_status === "unavailable"
              ? " (unavailable)"
              : "";
        return `<option value="${item.id}">${escapeHtml(item.name)} · ${escapeHtml(item.barcode)}${status}</option>`;
      }).join("")
    : '<option value="">No items available</option>';
};

const renderCategoryOptions = () => {
  const categories = state.type === "activity"
    ? state.options.activity_categories
    : state.options.categories;
  categorySelect.innerHTML = categories.length
    ? categories.map((category) => `<option value="${escapeHtml(category)}">${escapeHtml(category)}</option>`).join("")
    : '<option value="">No categories available</option>';
};

const selectedFields = () =>
  [...fieldGrid.querySelectorAll("input:checked")].map((input) => input.value);

const renderFields = (mode = "saved") => {
  const fields = currentFields();
  fieldGrid.innerHTML = fields.map((field) => {
    const checked = mode === "all" || (mode === "saved" && field.selected);
    return `<label class="field-option"><input type="checkbox" value="${field.key}" ${checked ? "checked" : ""} /><span>${field.label}</span></label>`;
  }).join("");
  updateSummary();
};

const scopeLabel = () => {
  if (scopeSelect.value === "category") {
    return categorySelect.value || "Choose a category";
  }
  if (scopeSelect.value === "item") {
    return itemSelect.selectedOptions[0]?.textContent || "Choose an item";
  }
  return state.type === "activity" ? "All recorded events" : "All items";
};

const updateUrl = () => {
  const url = new URL(window.location.href);
  url.search = "";
  url.searchParams.set("type", state.type);
  url.searchParams.set("scope", scopeSelect.value);
  if (scopeSelect.value === "category" && categorySelect.value) {
    url.searchParams.set("category", categorySelect.value);
  }
  if (scopeSelect.value === "item" && itemSelect.value) {
    url.searchParams.set("item_id", itemSelect.value);
  }
  window.history.replaceState({}, "", `${url.pathname}${url.search}`);
};

const updateSummary = () => {
  const count = selectedFields().length;
  fieldCount.textContent = `${count} of ${currentFields().length} fields selected`;
  summaryFields.textContent = count ? `${count} selected` : "None selected";
  summaryScope.textContent = scopeLabel();
  summaryTitle.textContent = state.type === "activity" ? "Item history CSV" : "Inventory CSV";
  summaryHelp.textContent = state.type === "activity"
    ? "The file contains permanent operational events, not catalogue checkouts."
    : "The file contains the latest saved values for each selected item.";
  exportError.textContent = "";
  updateUrl();
};

const updateScope = () => {
  categoryField.hidden = scopeSelect.value !== "category";
  itemField.hidden = scopeSelect.value !== "item";
  updateSummary();
};

const setType = (type) => {
  state.type = type;
  if (!state.options) return;
  renderItemOptions();
  renderCategoryOptions();
  historyNote.hidden = type !== "activity";
  includeRemovedRow.hidden = type !== "inventory";
  renderFields();
};

const applyQuery = () => {
  const query = new URLSearchParams(window.location.search);
  const type = query.get("type") === "activity" ? "activity" : "inventory";
  document.querySelector(`input[name="export_type"][value="${type}"]`).checked = true;
  state.type = type;
  renderItemOptions();
  renderCategoryOptions();
  const scope = ["all", "category", "item"].includes(query.get("scope"))
    ? query.get("scope")
    : "all";
  scopeSelect.value = scope;
  const availableCategories = type === "activity"
    ? state.options.activity_categories
    : state.options.categories;
  if (query.get("category") && availableCategories.includes(query.get("category"))) {
    categorySelect.value = query.get("category");
  }
  const availableItems = type === "activity" ? state.options.activity_items : state.options.items;
  if (query.get("item_id") && availableItems.some((item) => String(item.id) === query.get("item_id"))) {
    itemSelect.value = query.get("item_id");
  }
  historyNote.hidden = type !== "activity";
  includeRemovedRow.hidden = type !== "inventory";
  updateScope();
  renderFields();
};

const initialize = async () => {
  try {
    const user = await requestJson("/auth/me");
    if (!canManage(user)) {
      window.location.replace("/lendery");
      return;
    }
    document.querySelector("#account-name").textContent = capitalizeFirst(user.name);
    state.options = await requestJson("/lendery/export/options");
    applyQuery();
  } catch (error) {
    if (error.status === 401) {
      window.location.replace(`/login?next=${encodeURIComponent("/lendery/export")}`);
      return;
    }
    exportError.textContent = error.message;
    downloadButton.disabled = true;
  }
};

document.querySelectorAll('input[name="export_type"]').forEach((input) => {
  input.addEventListener("change", () => setType(input.value));
});
scopeSelect.addEventListener("change", updateScope);
categorySelect.addEventListener("change", updateSummary);
itemSelect.addEventListener("change", updateSummary);
includeRemoved.addEventListener("change", updateSummary);
fieldGrid.addEventListener("change", updateSummary);
document.querySelector("#select-all").addEventListener("click", () => renderFields("all"));
document.querySelector("#restore-defaults").addEventListener("click", () => renderFields("saved"));
document.querySelector("#clear-fields").addEventListener("click", () => renderFields("none"));
document.querySelector("#logout").addEventListener("click", async () => {
  await fetch("/auth/logout", { method: "POST" });
  window.location.assign("/home");
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const fields = selectedFields();
  if (!fields.length) {
    exportError.textContent = "Select at least one field to export.";
    return;
  }
  const payload = {
    fields,
    scope: scopeSelect.value,
    category: scopeSelect.value === "category" ? categorySelect.value : null,
    item_id: scopeSelect.value === "item" ? Number(itemSelect.value) : null,
  };
  if (state.type === "inventory") payload.include_removed = includeRemoved.checked;
  downloadButton.disabled = true;
  downloadButton.textContent = "Preparing CSV…";
  exportError.textContent = "";
  try {
    const response = await fetch(`/lendery/export/${state.type}.csv`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(typeof body.detail === "string" ? body.detail : "The export could not be created.");
    }
    const blob = await response.blob();
    const disposition = response.headers.get("content-disposition") || "";
    const filename = disposition.match(/filename="?([^";]+)"?/i)?.[1]
      || `lendery-${state.type}.csv`;
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.append(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  } catch (error) {
    exportError.textContent = error.message;
  } finally {
    downloadButton.disabled = false;
    downloadButton.innerHTML = '<span aria-hidden="true">⇩</span> Download CSV';
  }
});

initialize();
