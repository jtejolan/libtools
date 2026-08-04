const $ = (selector) => document.querySelector(selector);

const itemInitials = (name = "") =>
  name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((word) => word[0])
    .join("")
    .toUpperCase();

const form = $("#check-form");
const input = $("#check-input");
const result = $("#check-result");

const state = {
  components: [],
  checked: new Set(),
};

const showStatus = (message, isError = false) => {
  result.hidden = false;
  result.innerHTML = `<div class="check-status ${isError ? "is-error" : ""}">${escapeHtml(message)}</div>`;
};

const updateChecklistStatus = () => {
  const total = state.components.length;
  const checkedCount = state.checked.size;
  const percent = total ? Math.round((checkedCount / total) * 100) : 0;
  const countEl = $("#check-checklist-count");
  const messageEl = $("#check-checklist-message");
  const percentEl = $("#check-checklist-percent");
  const barEl = $("#check-checklist-bar");
  if (!countEl) return;
  countEl.textContent = `${checkedCount} of ${total} checked`;
  messageEl.textContent =
    checkedCount === total ? "Everything is accounted for" : "Tap each part as you find it";
  percentEl.textContent = `${percent}%`;
  barEl.style.width = `${percent}%`;
};

const renderChecklist = (components) => {
  if (!components.length) {
    return `<p class="check-checklist-empty">No parts are tracked for this item.</p>`;
  }
  return `
    <div class="check-checklist-status">
      <div>
        <strong id="check-checklist-count">0 of ${components.length} checked</strong>
        <span id="check-checklist-message">Tap each part as you find it</span>
      </div>
      <b id="check-checklist-percent">0%</b>
    </div>
    <div class="check-checklist-track"><span id="check-checklist-bar" style="width:0%"></span></div>
    <div class="check-part-list">${components
      .map(
        (component, index) => `<label class="check-part" data-part-index="${index}">
          <span class="check-part-visual">
            <input type="checkbox" data-check-part="${index}" aria-label="Mark ${escapeHtml(component.name)} as present" />
            ${
              component.image_url
                ? `<img src="${escapeHtml(component.image_url)}" alt="" loading="lazy" />`
                : `<span class="check-part-placeholder" aria-hidden="true">${escapeHtml(itemInitials(component.name))}</span>`
            }
            <span class="check-part-check" aria-hidden="true">✓</span>
          </span>
          <span class="check-part-info">
            <span class="check-part-name">${escapeHtml(component.name)}</span>
            <span class="check-part-qty">Qty ${component.quantity}</span>
            ${component.optional ? `<span class="check-part-optional">Optional</span>` : ""}
          </span>
        </label>`,
      )
      .join("")}</div>`;
};

const renderItem = (item) => {
  state.components = item.components;
  state.checked = new Set();
  result.hidden = false;
  result.innerHTML = `<div class="check-card">
    <div class="check-card-top">
      <span class="check-card-image">${
        item.image_url
          ? `<img src="${escapeHtml(item.image_url)}" alt="" />`
          : escapeHtml(itemInitials(item.name))
      }</span>
      <div class="check-card-heading">
        <h2>${escapeHtml(item.name)}</h2>
        ${item.category ? `<span class="check-category">${escapeHtml(item.category)}</span>` : ""}
      </div>
    </div>
    ${item.description ? `<p class="check-card-description">${escapeHtml(item.description)}</p>` : ""}
    ${
      item.manual_url
        ? `<a class="check-manual-link" href="${escapeHtml(item.manual_url)}" target="_blank" rel="noopener">View the manual ↗</a>`
        : ""
    }
    <div class="check-checklist">
      <div class="check-checklist-heading">
        <h3>What should be inside</h3>
        ${item.components.length ? `<button class="check-reset" type="button" id="check-reset">Reset</button>` : ""}
      </div>
      ${renderChecklist(item.components)}
    </div>
  </div>`;
};

const checkBarcode = async (barcode) => {
  showStatus("Looking that up…");
  try {
    const response = await fetch(
      `/api/public/lendery/items/barcode/${encodeURIComponent(barcode)}`,
      { cache: "no-store" },
    );
    if (!response.ok) {
      showStatus(`No item found for barcode "${barcode}".`, true);
      return;
    }
    const item = await response.json();
    renderItem(item);
  } catch (error) {
    showStatus("Something went wrong. Try again.", true);
  }
};

form.addEventListener("submit", (event) => {
  event.preventDefault();
  const barcode = input.value.trim();
  if (!barcode) return;
  checkBarcode(barcode);
});

result.addEventListener("change", (event) => {
  const checkbox = event.target.closest("[data-check-part]");
  if (!checkbox) return;
  const index = Number(checkbox.dataset.checkPart);
  if (checkbox.checked) state.checked.add(index);
  else state.checked.delete(index);
  checkbox.closest(".check-part")?.classList.toggle("checked", checkbox.checked);
  updateChecklistStatus();
});

result.addEventListener("click", (event) => {
  if (!event.target.closest("#check-reset")) return;
  state.checked.clear();
  result.querySelectorAll(".check-part").forEach((el) => {
    el.classList.remove("checked");
    el.querySelector("[data-check-part]").checked = false;
  });
  updateChecklistStatus();
});

input.focus({ preventScroll: true });
