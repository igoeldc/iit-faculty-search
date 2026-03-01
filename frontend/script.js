// ── State ──────────────────────────────────────────────────────────────────
let API_URL = 'http://localhost:8000';
let state = {
  query: '',
  department: '',
  facultyType: '',
  mode: 'hybrid',
  page: 0,
  limit: 20,
  total: 0,
  results: [],
  demoMode: false,
};

let searchTimer = null;

// ── Setup ─────────────────────────────────────────────────────────────────
async function connectToApi() {
  const input = document.getElementById('api-url-input').value.trim();
  if (input) API_URL = input.replace(/\/$/, '');

  try {
    const r = await fetch(`${API_URL}/api/health`);
    if (!r.ok) throw new Error('Bad response');
    const data = await r.json();
    hideSetup();
    await loadDepartments();
    await loadStats();
    doSearch();
  } catch(e) {
    alert(`Could not connect to API at ${API_URL}

Make sure the backend is running:
  uvicorn main:app --reload`);
  }
}

function loadDemoMode() {
  state.demoMode = true;
  hideSetup();
  injectDemoData();
}

function hideSetup() {
  document.getElementById('setup-screen').style.display = 'none';
}

// ── Demo data ──────────────────────────────────────────────────────────────
function injectDemoData() {
  const demoFaculty = [
    { id: 1, name: "Mustafa Bilgic", department: "Computer Science",
      titles: ["Chair, Department of Computer Science", "Professor of Computer Science", "Program Director, Master of Artificial Intelligence"],
      email: "mbilgic@illinoistech.edu", phone: "312.567.5143",
      research_areas: "Machine learning, probabilistic graphical models, active learning, link prediction",
      bio: "Dr. Bilgic's research focuses on machine learning and probabilistic reasoning. He works on developing algorithms for learning from data with structured uncertainty.",
      profile_url: "https://www.iit.edu/directory/people/mustafa-bilgic" },
    { id: 2, name: "Gady Agam", department: "Computer Science",
      titles: ["Associate Professor of Computer Science"],
      email: "agam@illinoistech.edu", phone: "312.567.5834",
      research_areas: "Computer vision, document image analysis, machine learning, medical image analysis",
      bio: "Gady Agam's research interests are in image analysis and machine learning with applications to document understanding and medical imaging.",
      profile_url: "https://www.iit.edu/directory/people/gady-agam" },
    { id: 3, name: "Matthew Bauer", department: "Computer Science",
      titles: ["Associate Chair", "Teaching Professor of Computer Science"],
      email: "bauerm@illinoistech.edu", phone: "312.567.5148",
      research_areas: "Software engineering, computing education, programming languages",
      bio: "Matthew Bauer focuses on computing education and software engineering pedagogy.",
      profile_url: "https://www.iit.edu/directory/people/matthew-bauer" },
    { id: 4, name: "André Bauer", department: "Computer Science",
      titles: ["Assistant Professor of Computer Science"],
      email: "abauer7@illinoistech.edu",
      research_areas: "Distributed systems, resource management, machine learning systems, cloud computing",
      bio: "André Bauer's research lies at the intersection of systems and machine learning, focusing on efficient resource management for distributed ML workloads.",
      profile_url: "https://www.iit.edu/directory/people/andre-bauer" },
    { id: 5, name: "Natacha DePaola", department: "Biomedical Engineering",
      titles: ["Professor of Biomedical Engineering", "Director, IDMET"],
      email: "ndepaola@illinoistech.edu",
      research_areas: "Cellular biomechanics, cardiovascular engineering, tissue engineering, mechanobiology",
      bio: "Prof. DePaola investigates the role of mechanical forces in cell biology and cardiovascular disease.",
      profile_url: "https://www.iit.edu/directory/people/natacha-depaola" },
    { id: 6, name: "Matthew Spenko", department: "Mechanical, Materials, and Aerospace Engineering",
      titles: ["Professor of Mechanical and Aerospace Engineering"],
      email: "mspenko@illinoistech.edu",
      research_areas: "Robotics, mechanical design, bio-inspired locomotion, controls, climbing robots",
      bio: "Matthew Spenko directs the Robotics Lab at Illinois Tech, working on bio-inspired mobile robots capable of climbing walls and traversing complex terrain.",
      profile_url: "https://www.iit.edu/directory/people/matthew-spenko" },
    { id: 7, name: "Ali Cinar", department: "Chemical and Biological Engineering",
      titles: ["Hyosung S. R. Cho Endowed Chair in Engineering", "Professor of Chemical Engineering", "Director, Center for Diabetes Research"],
      email: "cinar@illinoistech.edu",
      research_areas: "Biomedical systems control, artificial pancreas, diabetes management, biosensors",
      bio: "Ali Cinar's research focuses on intelligent systems for diabetes management, including automated insulin delivery systems.",
      profile_url: "https://www.iit.edu/directory/people/ali-cinar" },
    { id: 8, name: "Gruia Calinescu", department: "Computer Science",
      titles: ["Associate Professor of Computer Science"],
      email: "calinescu@illinoistech.edu", phone: "312.567.5273",
      research_areas: "Algorithms, approximation algorithms, combinatorial optimization, graph theory",
      bio: "Gruia Calinescu works on the design and analysis of algorithms, particularly approximation algorithms for NP-hard optimization problems.",
      profile_url: "https://www.iit.edu/directory/people/gruia-calinescu" },
    { id: 9, name: "Priyanka Sharma", department: "Stuart School of Business",
      titles: ["Associate Professor of Economics"],
      email: "psharma@illinoistech.edu",
      research_areas: "Finance, innovation, entrepreneurship, industrial organization, applied game theory",
      bio: "Priyanka Sharma's research applies game theory and econometrics to understand innovation, entrepreneurship, and market competition.",
      profile_url: "https://www.iit.edu/directory/people/priyanka-sharma" },
    { id: 10, name: "Fouad Teymour", department: "Chemical and Biological Engineering",
      titles: ["S.C. Johnson Professor of Chemical Engineering", "Director, Center for Complex Systems and Dynamics"],
      email: "fteymour@illinoistech.edu",
      research_areas: "Polymer engineering, nonlinear dynamics, complex systems, reaction engineering",
      bio: "Fouad Teymour studies complex dynamical behavior in chemical and biological systems.",
      profile_url: "https://www.iit.edu/directory/people/fouad-teymour" },
    { id: 11, name: "Ankit Srivastava", department: "Mechanical, Materials, and Aerospace Engineering",
      titles: ["Associate Professor"],
      email: "asrivastava@illinoistech.edu",
      research_areas: "Soft robotics, digital twins, augmented reality, smart materials",
      bio: "Ankit Srivastava researches soft and hybrid robotic systems and smart materials for next-generation applications.",
      profile_url: "https://www.iit.edu/directory/people/ankit-srivastava" },
    { id: 12, name: "Britt Burton-Freeman", department: "Food Science and Nutrition",
      titles: ["Professor, Food Science and Nutrition", "Chair, Department of Food Science and Nutrition", "Director, Center for Nutrition Research"],
      email: "bburton@illinoistech.edu",
      research_areas: "Nutritional biochemistry, diet and chronic disease, metabolic health, diabetes prevention",
      bio: "Britt Burton-Freeman leads research on how diet affects metabolic health and chronic disease prevention.",
      profile_url: "https://www.iit.edu/directory/people/britt-burton-freeman" },
  ];

  const depts = [...new Set(demoFaculty.map(f => f.department))].sort();
  const sel = document.getElementById('dept-filter');
  depts.forEach(d => {
    const opt = document.createElement('option');
    opt.value = d; opt.textContent = d;
    sel.appendChild(opt);
  });

  document.getElementById('header-stats').textContent = `${demoFaculty.length} faculty · demo mode`;

  state.results = demoFaculty;
  state.total = demoFaculty.length;
  renderResults();
  document.getElementById('results-bar').style.display = 'flex';
  document.getElementById('results-count').innerHTML = `Showing <strong>${demoFaculty.length}</strong> faculty`;
  window._demoFaculty = demoFaculty;
}

// ── API calls ─────────────────────────────────────────────────────────────
async function loadDepartments() {
  const r = await fetch(`${API_URL}/api/departments`);
  const data = await r.json();
  const sel = document.getElementById('dept-filter');
  data.departments.forEach(d => {
    const opt = document.createElement('option');
    opt.value = d; opt.textContent = d;
    sel.appendChild(opt);
  });
}

async function loadStats() {
  const r = await fetch(`${API_URL}/api/stats`);
  const data = await r.json();
  document.getElementById('header-stats').textContent =
    `${data.total_faculty} faculty · ${data.total_departments} departments`;
}

async function doSearch() {
  if (state.demoMode) { doSearchDemo(); return; }

  const params = new URLSearchParams({
    limit: state.limit,
    offset: state.page * state.limit,
    mode: state.mode,
  });
  if (state.query) params.set('q', state.query);
  if (state.department) params.set('department', state.department);
  if (state.facultyType) params.set('faculty_type', state.facultyType);

  showLoading();

  try {
    const r = await fetch(`${API_URL}/api/search?${params}`);
    const data = await r.json();
    state.results = data.results;
    state.total = data.total;
    renderResults();
    renderPagination();
    updateResultsBar();
  } catch(e) {
    showError(e);
  }
}

function doSearchDemo() {
  let all = window._demoFaculty || [];
  const q = state.query.toLowerCase();

  if (q) {
    all = all.filter(f => {
      const text = [f.name, f.department, ...(f.titles||[]), f.research_areas||'', f.bio||''].join(' ').toLowerCase();
      return text.includes(q);
    });
  }
  if (state.department) {
    all = all.filter(f => f.department === state.department);
  }
  if (state.facultyType) {
    all = all.filter(f => (f.titles||[]).some(t => t.toLowerCase().includes(state.facultyType.toLowerCase())));
  }

  state.results = all.slice(state.page * state.limit, (state.page + 1) * state.limit);
  state.total = all.length;
  renderResults();
  renderPagination();
  updateResultsBar();
}

// ── Render ────────────────────────────────────────────────────────────────
function renderResults() {
  const grid = document.getElementById('faculty-grid');
  grid.innerHTML = '';

  if (state.results.length === 0) {
    grid.innerHTML = `
      <div class="empty-state">
        <div class="empty-state-icon">🔍</div>
        <h3>No faculty found</h3>
        <p>Try adjusting your search terms, clearing filters, or switching search mode.</p>
      </div>`;
    return;
  }

  state.results.forEach(f => {
    grid.appendChild(createCard(f));
  });
}

function getInitials(name) {
  return name.split(' ').map(w => w[0]).filter(Boolean).slice(0,2).join('').toUpperCase();
}

function createCard(f) {
  const card = document.createElement('div');
  card.className = 'faculty-card';
  card.onclick = () => openModal(f);

  const titles = (f.titles || []).filter(t => !["Faculty","Media Expert","Staff"].includes(t));

  const avatarHtml = f.photo_url
    ? `<div class="avatar"><img src="${f.photo_url}" alt="${f.name}" onerror="this.parentElement.textContent='${getInitials(f.name)}'"></div>`
    : `<div class="avatar">${getInitials(f.name)}</div>`;

  const researchHtml = f.research_areas ? `
    <div class="card-research">
      <div class="card-research-label">Research</div>
      <div class="card-research-text">${f.research_areas}</div>
    </div>` : '';

  const emailHtml = f.email ? `<div class="card-email">${f.email}</div>` : `<div class="card-email" style="color:var(--rule)">no email listed</div>`;

  const scoreHtml = f._score ? `<div class="score-badge">${f._score.toFixed(2)}</div>` : '';

  card.innerHTML = `
    <div class="card-header">
      ${avatarHtml}
      <div class="card-name-block">
        <div class="card-name">${f.name}</div>
        <div class="card-dept">${f.department || ''}</div>
      </div>
    </div>
    ${titles.length ? `<div class="card-titles">${titles.slice(0,2).map(t => `<span class="card-title-badge">${t}</span>`).join('')}</div>` : ''}
    ${researchHtml}
    <div class="card-footer">
      ${emailHtml}
      ${f.profile_url ? `<a class="card-link" href="${f.profile_url}" target="_blank" onclick="e=>e.stopPropagation()">Profile →</a>` : ''}
      ${scoreHtml}
    </div>
  `;
  return card;
}

function showLoading() {
  const grid = document.getElementById('faculty-grid');
  grid.innerHTML = Array.from({length: 8}).map(() =>
    `<div class="skeleton-card"><div class="skeleton" style="height:16px;width:60%;margin-bottom:12px"></div>
     <div class="skeleton" style="height:12px;width:40%;margin-bottom:20px"></div>
     <div class="skeleton" style="height:60px"></div></div>`
  ).join('');
}

function showError(e) {
  document.getElementById('faculty-grid').innerHTML = `<div class="empty-state"><div class="empty-state-icon">⚠️</div><h3>Connection error</h3><p>${e.message}</p></div>`;
}

// ── Pagination ────────────────────────────────────────────────────────────
function renderPagination() {
  const total_pages = Math.ceil(state.total / state.limit);
  const pg = document.getElementById('pagination');
  pg.innerHTML = '';
  if (total_pages <= 1) return;

  const btn = (label, onclick, disabled=false, active=false) => {
    const b = document.createElement('button');
    b.className = 'page-btn' + (active ? ' active' : '');
    b.textContent = label;
    b.disabled = disabled;
    b.onclick = onclick;
    return b;
  };

  pg.appendChild(btn('←', () => { state.page--; doSearch(); }, state.page === 0));

  const start = Math.max(0, state.page - 2);
  const end = Math.min(total_pages - 1, state.page + 2);
  for (let i = start; i <= end; i++) {
    pg.appendChild(btn(i + 1, () => { state.page = i; doSearch(); }, false, i === state.page));
  }

  pg.appendChild(btn('→', () => { state.page++; doSearch(); }, state.page >= total_pages - 1));
}

// ── Results bar ───────────────────────────────────────────────────────────
function updateResultsBar() {
  const bar = document.getElementById('results-bar');
  bar.style.display = 'flex';

  const from = state.page * state.limit + 1;
  const to = Math.min((state.page + 1) * state.limit, state.total);
  document.getElementById('results-count').innerHTML =
    state.total === 0
      ? 'No results'
      : `Showing <strong>${from}–${to}</strong> of <strong>${state.total}</strong> faculty`;

  const chips = document.getElementById('active-filters');
  chips.innerHTML = '';

  const addChip = (label, clear) => {
    const chip = document.createElement('div');
    chip.className = 'filter-chip';
    chip.innerHTML = `${label}<button onclick="${clear}">×</button>`;
    chips.appendChild(chip);
  };

  if (state.query) addChip(`"${state.query}"`, "clearQuery()");
  if (state.department) addChip(state.department, "clearDept()");
  if (state.facultyType) addChip(state.facultyType, "clearType()");

  const hasFilters = state.query || state.department || state.facultyType;
  document.getElementById('clear-all-btn').style.display = hasFilters ? 'block' : 'none';
}

function clearQuery() { state.query = ''; state.page = 0; document.getElementById('search-input').value = ''; doSearch(); }
function clearDept() { state.department = ''; state.page = 0; document.getElementById('dept-filter').value = ''; doSearch(); }
function clearType() { state.facultyType = ''; state.page = 0; document.getElementById('type-filter').value = ''; doSearch(); }
function clearAll() { clearQuery(); clearDept(); clearType(); }

// ── Modal ─────────────────────────────────────────────────────────────────
function openModal(f) {
  const titles = (f.titles || []).filter(t => !["Faculty","Media Expert","Staff"].includes(t));
  const avatarHtml = f.photo_url
    ? `<div class="modal-avatar"><img src="${f.photo_url}" alt="${f.name}" onerror="this.parentElement.textContent='${getInitials(f.name)}'"></div>`
    : `<div class="modal-avatar">${getInitials(f.name)}</div>`;

  document.getElementById('modal-hero').innerHTML = `
    ${avatarHtml}
    <div style="flex:1;min-width:0">
      <div class="modal-name">${f.name}</div>
      <div class="modal-dept">${f.department || ''}</div>
      ${titles.length ? `<ul class="modal-title-list">${titles.map(t => `<li>${t}</li>`).join('')}</ul>` : ''}
    </div>
    <button class="modal-close" onclick="closeModal()">×</button>
  `;

  let bodyHtml = '';

  // Research areas
  if (f.research_areas) {
    bodyHtml += `<div class="modal-section">
      <div class="modal-section-title">Research Areas</div>
      <div class="modal-section-body">${f.research_areas}</div>
    </div>`;
  }

  // Bio
  if (f.bio) {
    bodyHtml += `<div class="modal-section">
      <div class="modal-section-title">Biography</div>
      <div class="modal-section-body">${f.bio}</div>
    </div>`;
  }

  // Publications
  if (f.publications_snippet) {
    bodyHtml += `<div class="modal-section">
      <div class="modal-section-title">Selected Publications</div>
      <div class="modal-section-body">${f.publications_snippet}</div>
    </div>`;
  }

  // Education
  if (f.education) {
    bodyHtml += `<div class="modal-section">
      <div class="modal-section-title">Education</div>
      <div class="modal-section-body">${f.education}</div>
    </div>`;
  }

  // Contact
  let contactHtml = '';
  if (f.email) contactHtml += `<div class="contact-row"><div class="contact-label">Email</div><div class="contact-value"><a href="mailto:${f.email}">${f.email}</a></div></div>`;
  if (f.phone) contactHtml += `<div class="contact-row"><div class="contact-label">Phone</div><div class="contact-value">${f.phone}</div></div>`;
  if (f.profile_url) contactHtml += `<div class="contact-row"><div class="contact-label">Profile</div><div class="contact-value"><a href="${f.profile_url}" target="_blank">View IIT Profile →</a></div></div>`;

  if (contactHtml) {
    bodyHtml += `<div class="modal-section">
      <div class="modal-section-title">Contact</div>
      <div class="modal-section-body">${contactHtml}</div>
    </div>`;
  }

  // External links
  const links = f.external_links || {};
  if (typeof links === 'object' && Object.keys(links).length) {
    const linkHtml = Object.entries(links).map(([k, v]) => {
      const label = { google_scholar: '🎓 Google Scholar', github: '💻 GitHub', website: '🌐 Website', homepage: '🌐 Homepage' }[k] || k;
      return `<a class="ext-link" href="${v}" target="_blank">${label}</a>`;
    }).join('');
    bodyHtml += `<div class="modal-section">
      <div class="modal-section-title">Links</div>
      <div class="ext-links">${linkHtml}</div>
    </div>`;
  }

  if (!bodyHtml) {
    bodyHtml = `<p style="color:var(--ink-soft);font-size:14px;padding-top:8px">No additional information available. <a href="${f.profile_url}" target="_blank" style="color:var(--crimson)">View full profile →</a></p>`;
  }

  document.getElementById('modal-body').innerHTML = bodyHtml;
  document.getElementById('modal-overlay').classList.add('open');
  document.body.style.overflow = 'hidden';
}

function closeModal() {
  document.getElementById('modal-overlay').classList.remove('open');
  document.body.style.overflow = '';
}

function closeModalOutside(e) {
  if (e.target === document.getElementById('modal-overlay')) closeModal();
}

// ── Event listeners ───────────────────────────────────────────────────────
document.getElementById('search-input').addEventListener('input', e => {
  state.query = e.target.value;
  state.page = 0;
  clearTimeout(searchTimer);
  searchTimer = setTimeout(doSearch, 350);
});

document.getElementById('dept-filter').addEventListener('change', e => {
  state.department = e.target.value;
  state.page = 0;
  doSearch();
});

document.getElementById('type-filter').addEventListener('change', e => {
  state.facultyType = e.target.value;
  state.page = 0;
  doSearch();
});

document.querySelectorAll('.mode-tab').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.mode-tab').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    state.mode = btn.dataset.mode;
    state.page = 0;
    doSearch();
  });
});

document.addEventListener('keydown', e => {
  if (e.key === 'Escape') closeModal();
});
