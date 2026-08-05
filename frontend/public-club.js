const $=(s)=>document.querySelector(s);
const slug=decodeURIComponent(location.pathname.split("/").filter(Boolean).pop()||"");
const formatDate=(value)=>new Intl.DateTimeFormat("en-CA",{weekday:"long",month:"long",day:"numeric",year:"numeric"}).format(new Date(`${value}T12:00:00`));
const initials=(name)=>name.split(/\s+/).filter(Boolean).slice(0,2).map((word)=>word[0]).join("").toUpperCase();
const safeImageUrl=(value)=>{if(!value)return "";try{const url=new URL(value);return ["http:","https:"].includes(url.protocol)?url.href:"";}catch{return "";}};
const renderShelf=(books)=>{
  const section=$("#shelf-section");
  if(!books.length){section.hidden=true;return;}
  section.hidden=false;
  $("#shelf-grid").innerHTML=books.map((book)=>{
    const cover=safeImageUrl(book.cover_image_url);
    return `<div class="shelf-item"><div class="shelf-cover">${cover?`<img src="${escapeHtml(cover)}" alt="Cover of ${escapeHtml(book.title)}" loading="lazy" />`:escapeHtml(initials(book.title))}</div><strong>${escapeHtml(book.title)}</strong><small>${escapeHtml(book.author)}</small></div>`;
  }).join("");
};
(async()=>{const response=await fetch(`/api/public/clubs/${encodeURIComponent(slug)}`,{cache:"no-store"});if(!response.ok){$("#club-name").textContent="Club not found";$("#club-description").textContent="This club page is unavailable or private.";return;}const club=await response.json();document.title=`${club.name} — Library Tools`;$("#club-name").textContent=club.name;$("#club-description").textContent=club.description||"A community book club.";renderShelf(club.shelf||[]);const meeting=club.upcoming_meeting;if(!meeting){$("#meeting-details").hidden=false;$("#meeting-details").innerHTML="<strong>Next meeting coming soon</strong><span>Check back for the next selection.</span>";return;}$("#meeting-details").hidden=false;$("#meeting-details").innerHTML=`<p class="eyebrow">Next meeting</p><strong>${escapeHtml(meeting.book.title)}</strong><span>by ${escapeHtml(meeting.book.author)} · ${escapeHtml(formatDate(meeting.meeting_date))}${meeting.meeting_time?` · ${escapeHtml(meeting.meeting_time)}`:""}${meeting.location?` · ${escapeHtml(meeting.location)}`:""}</span>`;const cover=meeting.book.cover_image_url;if(cover){const image=new Image();image.alt=`Cover of ${meeting.book.title}`;image.src=cover;$("#public-cover").replaceChildren(image);}else{$("#public-cover").textContent=meeting.book.title.split(/\s+/).slice(0,2).map(word=>word[0]).join("");}})();
