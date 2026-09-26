(() => {
  "use strict";
  const opening = document.getElementById("world-opening");
  let timer;
  const markSeen = () => { try { localStorage.setItem("sparkcraft:opening:v1", "seen"); } catch {} };
  let exiting = false;
  const shell = document.querySelector(".studio-shell");
  const dismiss = async () => {
    if (exiting || !opening.open) return;
    exiting = true; clearTimeout(timer); markSeen();
    const source = opening.querySelector(".craft-opening img"), target = document.querySelector(".craft-logo");
    let flyer;
    try {
      if (!matchMedia("(prefers-reduced-motion: reduce)").matches && target.getBoundingClientRect().width) {
        const a = source.getBoundingClientRect(), b = target.getBoundingClientRect();
        flyer = source.cloneNode(); flyer.className = "opening-flyer";
        Object.assign(flyer.style, {left:`${a.left}px`,top:`${a.top}px`,width:`${a.width}px`,height:`${a.height}px`}); opening.append(flyer); source.style.visibility="hidden";
        opening.classList.add("opening-departing"); shell.style.opacity="1";
        await flyer.animate([{transform:"translate(0,0) scale(1)"},{transform:`translate(${b.left-a.left}px,${b.top-a.top}px) scale(${b.width/a.width})`}], {duration:950,easing:"cubic-bezier(.22,.75,.2,1)",fill:"forwards"}).finished;
      }
    } finally { flyer?.remove(); source.style.visibility=""; opening.close(); opening.classList.remove("opening-departing"); shell.style.opacity=""; exiting=false; }
  };
  const play = () => { if (exiting) return; clearTimeout(timer); shell.style.opacity="0"; opening.showModal(); timer=setTimeout(dismiss, matchMedia("(prefers-reduced-motion: reduce)").matches ? 1200 : 6500); };
  document.getElementById("opening-skip").addEventListener("click", dismiss);
  document.getElementById("opening-replay").addEventListener("click", play);
  opening.addEventListener("cancel", event => { event.preventDefault(); dismiss(); });
  let seen = false; try { seen = localStorage.getItem("sparkcraft:opening:v1") === "seen"; } catch {}
  if (!seen) play();
  for (const view of ["development", "knowledge"]) {
    const hero = document.querySelector(`#${view}-view .section-intro`);
    const landscape = document.createElement("div"); landscape.className = `voxel-landscape ${view}`; landscape.setAttribute("aria-hidden", "true");
    landscape.innerHTML = '<div class="land-cloud"></div><div class="land-sun"></div><div class="block block-a"></div><div class="block block-b"></div><div class="block block-c"></div><div class="pixel-tree"><i></i></div><div class="pixel-flower"></div><div class="land-label">BUILD YOUR WORLD</div>';
    const old = hero.querySelector(".voxel"); if (old) old.remove(); hero.append(landscape);
  }
  const heading = document.getElementById("development-title"); heading.replaceChildren(document.createTextNode("每个世界，")); const em = document.createElement("em"); em.textContent = "始于一个想法。"; heading.append(em);
})();
