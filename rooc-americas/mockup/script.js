const classes = [
  { name: "LORD KNIGHT", filter: ["frente", "dano"], role: "LINHA DE FRENTE", level: "COMPLEXIDADE BAIXA–MÉDIA", copy: "Combate físico, resistência e rotas de lança ou dano corpo a corpo." },
  { name: "PALADIN", filter: ["frente", "suporte"], role: "PROTEÇÃO", level: "COMPLEXIDADE MÉDIA", copy: "Escudos, proteção do grupo e rotas de tank ou dano sagrado." },
  { name: "HIGH WIZARD", filter: ["dano", "controle"], role: "DANO EM ÁREA", level: "COMPLEXIDADE MÉDIA", copy: "Magia elemental, limpeza de ondas e controle de espaço." },
  { name: "PROFESSOR", filter: ["dano", "controle"], role: "CONTROLE MÁGICO", level: "COMPLEXIDADE ALTA", copy: "Autocast, Psychic Wave, recursos e ferramentas táticas." },
  { name: "SNIPER", filter: ["dano"], role: "DANO À DISTÂNCIA", level: "COMPLEXIDADE BAIXA–MÉDIA", copy: "Farm seguro, ataque constante, falcão ou armadilhas." },
  { name: "MINSTREL", filter: ["suporte", "controle"], role: "SUPORTE MUSICAL", level: "COMPLEXIDADE MÉDIA", copy: "Buffs, utilidade e contribuição física à distância." },
  { name: "GYPSY", filter: ["suporte", "controle"], role: "CONTROLE E SUPORTE", level: "COMPLEXIDADE MÉDIA", copy: "Danças, debuffs e pressão à distância em grupo." },
  { name: "ASSASSIN CROSS", filter: ["dano"], role: "EXPLOSÃO FÍSICA", level: "COMPLEXIDADE MÉDIA", copy: "Crítico, veneno, velocidade e eliminação de alvo único." },
  { name: "STALKER", filter: ["dano", "controle"], role: "ADAPTAÇÃO", level: "COMPLEXIDADE ALTA", copy: "Cópia de habilidades, mobilidade e disrupção tática." },
  { name: "HIGH PRIEST", filter: ["suporte"], role: "CURA E SUSTENTAÇÃO", level: "COMPLEXIDADE MÉDIA", copy: "Cura, buffs, ressurreição e estabilidade de equipe." },
  { name: "CHAMPION", filter: ["dano", "controle"], role: "BURST DE ALVO ÚNICO", level: "COMPLEXIDADE ALTA", copy: "Combos, esferas espirituais e finalizações de alto impacto." },
  { name: "WHITESMITH", filter: ["frente", "dano"], role: "DANO E UTILIDADE", level: "COMPLEXIDADE MÉDIA", copy: "Armas, buffs, combate físico e identidade mercante." },
  { name: "BIOCHEMIST", filter: ["dano", "controle"], role: "DANO QUÍMICO", level: "COMPLEXIDADE ALTA", copy: "Acid Demonstration, plantas e preparação especializada." },
  { name: "SUMMONER DORAM", filter: ["dano", "suporte", "controle"], role: "FLEXÍVEL", level: "COMPLEXIDADE A CONFIRMAR", copy: "Caminhos internos de dano, suporte e sobrevivência." }
];

const rail = document.querySelector("#class-rail");
const filters = document.querySelectorAll("[data-filter]");
const detail = {
  name: document.querySelector("#detail-name"),
  copy: document.querySelector("#detail-copy"),
  role: document.querySelector("#detail-role"),
  level: document.querySelector("#detail-level")
};

function renderClasses() {
  rail.innerHTML = classes.map((item, index) => `
    <button class="class-card${index === 0 ? " active" : ""}" type="button" data-index="${index}" data-groups="${item.filter.join(" ")}">
      <span class="emblem-crop" aria-hidden="true" style="--x:${index % 7 * 16.666667}%;--y:${18 + Math.floor(index / 7) * 64}%"></span>
      <strong>${item.name}</strong>
    </button>`).join("");
}

function selectClass(index) {
  const item = classes[index];
  document.querySelectorAll(".class-card").forEach((card, cardIndex) => card.classList.toggle("active", cardIndex === index));
  detail.name.textContent = item.name;
  detail.copy.textContent = item.copy;
  detail.role.textContent = item.role;
  detail.level.textContent = item.level;
}

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

const menu = document.querySelector(".menu-toggle");
const nav = document.querySelector("#site-nav");
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
