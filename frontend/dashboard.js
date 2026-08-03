const $=(s)=>document.querySelector(s);
const request=async(url,options={})=>{const response=await fetch(url,{...options,cache:"no-store",headers:{...(options.body?{"Content-Type":"application/json"}:{}),...options.headers}});if(response.status===204)return null;const body=await response.json().catch(()=>({}));if(!response.ok)throw Object.assign(new Error(typeof body.detail==="string"?body.detail:body.detail?.[0]?.msg||"Something went wrong."),{status:response.status});return body;};
const toast=(message)=>{const el=$("#toast");el.textContent=message;el.classList.add("show");clearTimeout(toast.timer);toast.timer=setTimeout(()=>el.classList.remove("show"),2600);};

const lenderyCard=(tools)=>{
  const editor=tools.has("lendery_manage");
  return `<a class="dash-card dash-lendery is-link" href="/lendery"><div class="dash-card-top"><span class="dash-card-icon"><img src="/static/assets/lendery-logo-symbol-v3.png?v=4" alt=""/></span><span class="status">${editor?"Editor":"Viewer"}</span></div><h2>Lendery</h2><p>Check lendable inventory${editor?", edit records, and manage components":" and operate item checklists"}.</p><span class="dash-card-cta">Open inventory <b aria-hidden="true">→</b></span></a>`;
};

const bookclubCard=(user,tools)=>{
  if(!tools.has("bookclub")){
    return `<div class="dash-card dash-bookclub locked"><div class="dash-card-top"><span class="dash-card-icon"><img src="/static/assets/book-club-manager-logo-v2.png?v=1" alt=""/></span><span class="status muted">No access</span></div><h2>Book Club Manager</h2><p>Manage clubs, meetings, participants, books, messages, and attendance.</p><span class="dash-card-cta">Ask an admin for access</span></div>`;
  }
  const note=user.role==="admin"?"All clubs (admin)":user.clubs.length?`Your clubs: ${user.clubs.join(", ")}`:"No club selected yet — open the manager to pick one.";
  return `<a class="dash-card dash-bookclub is-link" href="/bookclub"><div class="dash-card-top"><span class="dash-card-icon"><img src="/static/assets/book-club-manager-logo-v2.png?v=1" alt=""/></span><span class="status on-dark">Member</span></div><h2>Book Club Manager</h2><p>${note}</p><span class="dash-card-cta">Open manager <b aria-hidden="true">→</b></span></a>`;
};

const storytimeCard=()=>`<div class="dash-card dash-storytime locked"><div class="dash-card-top"><span class="dash-card-icon"><img src="/static/assets/storytime-studio-logo.png?v=1" alt=""/></span><span class="status muted">Coming soon</span></div><h2>Storytime Studio</h2><p>A planned workspace for storytime resources and outlines.</p><span class="dash-card-cta">In development</span></div>`;

const accountCard=()=>`<a class="dash-card is-link" href="/account"><div class="dash-card-top"><span class="dash-card-icon" aria-hidden="true">⚙</span><span class="status muted">Settings</span></div><h2>Account</h2><p>Change your password, manage your recovery code, and review your sign-in details.</p><span class="dash-card-cta">Manage account <b aria-hidden="true">→</b></span></a>`;

const renderDashboard=(user)=>{
  $("#welcome-heading").textContent=`Welcome, ${user.username}`;
  $("#admin-link").hidden=user.role!=="admin";
  const tools=new Set(user.tools);
  if(user.role==="admin"){tools.add("bookclub");tools.add("lendery_manage");}
  $("#tool-grid").innerHTML=[lenderyCard(tools),bookclubCard(user,tools),storytimeCard(),accountCard()].join("");
};

$("#logout").addEventListener("click",async()=>{await request("/auth/logout",{method:"POST"});location.href="/login";});

(async()=>{
  try{
    renderDashboard(await request("/auth/me"));
  }catch(error){
    if(error.status===401){location.href="/login";return;}
    toast(error.message);
  }
})();
