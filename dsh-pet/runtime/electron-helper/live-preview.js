/* Opt-in production preview: update animation pools without rebuilding the sprite. */
'use strict';

(function () {
  function animationNames(a) {
    const names = [...a.idle, ...a.turn, ...a.drag, ...a.clicks, ...a.moves.actions.map((m) => m.name)];
    for (const c of a.categories) names.push(...c.actions);
    for (const pool of Object.values(a.events)) for (const slot of pool) names.push(...(Array.isArray(slot) ? slot : [slot]));
    return new Set(names);
  }

  function menuLabels(tree) {
    return tree.map((node) => ({ ...node,
      label: node.anim ? node.label.replace(/__v_[a-f0-9]{12}$/, '') : node.label,
      ...(node.children ? { children: menuLabels(node.children) } : {}),
    }));
  }

  function applyAnimations(sprite, pet) {
    const signature = JSON.stringify([pet.animations, pet.animationWeights, pet.fixedEnabled]);
    const changed = sprite.livePreviewSignature !== signature;
    const names = animationNames(pet.animations);
    sprite.pet = pet;
    sprite.animations = pet.animations;
    sprite.weights = pet.animationWeights;
    sprite.livePreviewSignature = signature;
    // Immutable versioned files remain on disk. Let an old version finish once,
    // then the ordinary idle chain selects the updated pools. Never reset position,
    // facing, drag/throw state, the video buffers, or an active window movement.
    if (!names.has(sprite.anim)) {
      const front = sprite.front === 0 ? sprite.videoA : sprite.videoB;
      if (front) {
        front.loop = false;
        front.onended = () => sprite.handleEnded();
      }
    }
    return changed;
  }

  if (typeof module !== 'undefined') module.exports = { animationNames, menuLabels, applyAnimations };
  if (typeof window === 'undefined') return;
  window.PetLivePreview = { menuLabels };
  if (!CONFIG.livePreview) return;
  let busy = false;
  async function refreshPreview() {
    if (busy || sprites.length === 0) return;
    busy = true;
    try {
      const next = await loadConfig();
      for (const sprite of sprites) {
        const pet = next.pets.find((p) => p.id === sprite.pet.id);
        if (pet && applyAnimations(sprite, pet)) {
          window.__dshPetDebug.livePreviewUpdates = (window.__dshPetDebug.livePreviewUpdates || 0) + 1;
          window.__dshPetDebug.livePreviewAnimations = animationNames(pet.animations).size;
          console.info('[dsh-pet] live preview updated: ' + animationNames(pet.animations).size + ' animations');
        }
      }
      config = next;
    } catch (error) {
      console.warn('[dsh-pet] live preview update deferred: ' + String(error));
    } finally {
      busy = false;
    }
  }
  const timer = setInterval(() => void refreshPreview(), 2000);
  window.addEventListener('beforeunload', () => clearInterval(timer), { once: true });
})();
