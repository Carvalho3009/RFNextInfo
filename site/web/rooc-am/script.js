const classes = [
  { name: "LORD KNIGHT", anchor: "lord-knight", filter: ["frente", "dano"], role: "LINHA DE FRENTE", level: "COMPLEXIDADE BAIXA–MÉDIA", copy: "Combate físico, resistência e rotas de lança ou dano corpo a corpo." },
  { name: "PALADIN", anchor: "paladin", filter: ["frente", "suporte"], role: "PROTEÇÃO", level: "COMPLEXIDADE MÉDIA", copy: "Escudos, proteção do grupo e rotas de tank ou dano sagrado." },
  { name: "HIGH WIZARD", anchor: "high-wizard", filter: ["dano", "controle"], role: "DANO EM ÁREA", level: "COMPLEXIDADE MÉDIA", copy: "Magia elemental, limpeza de ondas e controle de espaço." },
  { name: "PROFESSOR", anchor: "professor", filter: ["dano", "controle"], role: "CONTROLE MÁGICO", level: "COMPLEXIDADE ALTA", copy: "Autocast, Psychic Wave, recursos e ferramentas táticas." },
  { name: "SNIPER", anchor: "sniper", filter: ["dano"], role: "DANO À DISTÂNCIA", level: "COMPLEXIDADE BAIXA–MÉDIA", copy: "Farm seguro, ataque constante, falcão ou armadilhas." },
  { name: "MINSTREL", anchor: "minstrel", filter: ["suporte", "controle"], role: "SUPORTE MUSICAL", level: "COMPLEXIDADE MÉDIA", copy: "Buffs, utilidade e contribuição física à distância." },
  { name: "GYPSY", anchor: "gypsy", filter: ["suporte", "controle"], role: "CONTROLE E SUPORTE", level: "COMPLEXIDADE MÉDIA", copy: "Danças, debuffs e pressão à distância em grupo." },
  { name: "ASSASSIN CROSS", anchor: "assassin-cross", filter: ["dano"], role: "EXPLOSÃO FÍSICA", level: "COMPLEXIDADE MÉDIA", copy: "Crítico, veneno, velocidade e eliminação de alvo único." },
  { name: "STALKER", anchor: "stalker", filter: ["dano", "controle"], role: "ADAPTAÇÃO", level: "COMPLEXIDADE ALTA", copy: "Cópia de habilidades, mobilidade e disrupção tática." },
  { name: "HIGH PRIEST", anchor: "high-priest", filter: ["suporte"], role: "CURA E SUSTENTAÇÃO", level: "COMPLEXIDADE MÉDIA", copy: "Cura, buffs, ressurreição e estabilidade de equipe." },
  { name: "CHAMPION", anchor: "champion", filter: ["dano", "controle"], role: "BURST DE ALVO ÚNICO", level: "COMPLEXIDADE ALTA", copy: "Combos, esferas espirituais e finalizações de alto impacto." },
  { name: "WHITESMITH", anchor: "whitesmith-mastersmith", filter: ["frente", "dano"], role: "DANO E UTILIDADE", level: "COMPLEXIDADE MÉDIA", copy: "Armas, buffs, combate físico e identidade mercante." },
  { name: "BIOCHEMIST", anchor: "creator-biochemist", filter: ["dano", "controle"], role: "DANO QUÍMICO", level: "COMPLEXIDADE ALTA", copy: "Acid Demonstration, plantas e preparação especializada." },
  { name: "SUMMONER DORAM", anchor: "summoner-doram", filter: ["dano", "suporte", "controle"], role: "FLEXÍVEL", level: "COMPLEXIDADE A CONFIRMAR", copy: "Caminhos internos de dano, suporte e sobrevivência." }
];
// ponytail: o sprite original invade cinco células; recortar a borda evita duplicar 14 assets.
const clippedEmblems = new Set([2, 3, 4, 9, 10]);

const rail = document.querySelector("#class-rail");
const filters = document.querySelectorAll("[data-filter]");
const detail = {
  name: document.querySelector("#detail-name"),
  copy: document.querySelector("#detail-copy"),
  role: document.querySelector("#detail-role"),
  level: document.querySelector("#detail-level"),
  link: document.querySelector("#detail-link")
};

function renderClasses() {
  if (!rail) return;
  rail.innerHTML = classes.map((item, index) => {
    return `<button class="class-card${index === 0 ? " active" : ""}" type="button" data-index="${index}" data-groups="${item.filter.join(" ")}">
      <span class="emblem-crop" aria-hidden="true"><span class="emblem-cell${clippedEmblems.has(index) ? " cut-left" : ""}"><img src="../assets/class-emblems.png" alt="" decoding="sync"></span></span>
      <strong>${item.name}</strong>
    </button>`;
  }).join("");
}

function selectClass(index) {
  const item = classes[index];
  document.querySelectorAll(".class-card").forEach((card, cardIndex) => card.classList.toggle("active", cardIndex === index));
  detail.name.textContent = item.name;
  detail.copy.textContent = item.copy;
  detail.role.textContent = item.role;
  detail.level.textContent = item.level;
  detail.link.href = `classes.html#${item.anchor}`;
}

const quiz = document.querySelector("#class-quiz");
if (quiz) {
  const rules = {
    frontline: [0, 1, 11], damage: [0, 2, 3, 4, 7, 10, 11, 12, 13], support: [1, 5, 6, 9, 13], control: [2, 3, 5, 6, 8, 10, 12, 13],
    melee: [0, 1, 7, 8, 10, 11], ranged: [2, 3, 4, 5, 6, 9, 12, 13], either: classes.map((_, index) => index),
    steady: [0, 4, 7, 11], burst: [2, 7, 10, 12], tactical: [3, 6, 8, 13], team: [1, 5, 6, 9],
    simple: [0, 4], balanced: [1, 2, 5, 6, 7, 9, 11], advanced: [3, 8, 10, 12, 13],
    solo: [0, 2, 4, 7, 11, 13], group: [1, 3, 5, 6, 9, 12], pvp: [1, 3, 5, 6, 8, 9, 10, 13], mvp: [0, 4, 7, 10, 12]
  };
  quiz.addEventListener("submit", event => {
    event.preventDefault();
    const scores = classes.map(() => 0);
    for (const [question, answer] of new FormData(quiz)) {
      rules[answer].forEach(index => scores[index] += question === "role" ? 3 : 1);
    }
    const ranking = scores.map((score, index) => ({ score, index })).sort((a, b) => b.score - a.score || a.index - b.index);
    const winner = classes[ranking[0].index];
    selectClass(ranking[0].index);
    document.querySelector("#quiz-result-name").textContent = winner.name;
    document.querySelector("#quiz-result-copy").textContent = winner.copy;
    document.querySelector("#quiz-result-alternatives").textContent = `Alternativas próximas: ${classes[ranking[1].index].name} e ${classes[ranking[2].index].name}.`;
    document.querySelector("#quiz-result-link").href = `classes.html#${winner.anchor}`;
    document.querySelector("#quiz-result").hidden = false;
  });
}

const checklist = document.querySelector("[data-user-checklist]");
if (checklist) {
  const profileForm = checklist.querySelector("#profile-form");
  const profileInput = checklist.querySelector("#profile-name");
  const profileList = checklist.querySelector("#saved-profiles");
  const status = checklist.querySelector("#checklist-status");
  const reset = checklist.querySelector("#reset-checklist");
  const boxes = [...checklist.querySelectorAll("[data-checklist-item]")];
  const storage = {
    get(key, fallback) { try { const value = localStorage.getItem(key); return value === null ? fallback : JSON.parse(value); } catch { return fallback; } },
    set(key, value) { try { localStorage.setItem(key, JSON.stringify(value)); } catch {} }
  };
  let profiles = storage.get("rooc:checklist:profiles", []);
  let currentProfile = "";
  const profileKey = profile => encodeURIComponent(profile.normalize("NFKC").toLocaleLowerCase("pt-BR"));
  const stateKey = profile => `rooc:checklist:${profileKey(profile)}`;
  const taskKey = box => box.nextElementSibling.textContent.trim();

  function renderProfiles() {
    profileList.replaceChildren(...profiles.map(profile => Object.assign(document.createElement("option"), { value: profile })));
  }
  function updateStatus() {
    status.textContent = currentProfile ? `${currentProfile}: ${boxes.filter(box => box.checked).length} de ${boxes.length} concluídas.` : "Escolha um perfil local para começar.";
  }
  function loadProfile(profile) {
    currentProfile = profile;
    const saved = storage.get(stateKey(profile), {});
    boxes.forEach(box => { box.disabled = false; box.checked = Boolean(saved[taskKey(box)]); });
    storage.set("rooc:checklist:last", profile);
    updateStatus();
  }
  function saveProgress() {
    if (!currentProfile) return;
    storage.set(stateKey(currentProfile), Object.fromEntries(boxes.map(box => [taskKey(box), box.checked])));
    updateStatus();
  }

  renderProfiles();
  boxes.forEach(box => box.addEventListener("change", saveProgress));
  profileForm.addEventListener("submit", event => {
    event.preventDefault();
    const entered = profileInput.value.trim().slice(0, 32);
    if (!entered) return;
    const existing = profiles.find(profile => profileKey(profile) === profileKey(entered));
    const profile = existing || entered;
    if (!existing) { profiles.push(profile); storage.set("rooc:checklist:profiles", profiles); renderProfiles(); }
    profileInput.value = profile;
    loadProfile(profile);
  });
  reset.addEventListener("click", () => {
    if (!currentProfile) return;
    boxes.forEach(box => { box.checked = false; });
    saveProgress();
  });

  const lastProfile = storage.get("rooc:checklist:last", "");
  if (lastProfile) { profileInput.value = lastProfile; loadProfile(lastProfile); }
  else { boxes.forEach(box => { box.disabled = true; }); updateStatus(); }
}

if (rail) {
  renderClasses();
  rail.addEventListener("click", event => {
    const card = event.target.closest(".class-card");
    if (card) selectClass(Number(card.dataset.index));
  });

  filters.forEach(button => button.addEventListener("click", () => {
    filters.forEach(item => item.classList.toggle("active", item === button));
    const filter = button.dataset.filter;
    document.querySelectorAll(".class-card").forEach(card => {
      card.hidden = filter !== "todas" && !card.dataset.groups.split(" ").includes(filter);
    });
  }));
}

const menu = document.querySelector(".menu-toggle");
const nav = document.querySelector("#site-nav");
if (menu && nav) {
  menu.addEventListener("click", () => {
    const open = menu.getAttribute("aria-expanded") === "true";
    menu.setAttribute("aria-expanded", String(!open));
    nav.classList.toggle("open", !open);
  });
  nav.addEventListener("click", event => {
    if (event.target.matches("a")) {
      menu.setAttribute("aria-expanded", "false");
      nav.classList.remove("open");
    }
  });
}
