// =================================================================
// MODULE: CALENDAR DAILY VIEW
// =================================================================
document.addEventListener("DOMContentLoaded", function () {
    // CORRECTION 1: On cible le nouveau conteneur principal du calendrier
    const scheduleContainer = document.querySelector('.daily-schedule');
    if (!scheduleContainer) return;

    // Cette partie pour l'édition depuis le panier reste valide
    const editDataJSON = sessionStorage.getItem('editReservationData');
    if (editDataJSON) {
        try {
            const editData = JSON.parse(editDataJSON);
            if (typeof openReservationModal === 'function') {
                openReservationModal(editData.date, editData.editingGroupId);
            }
        } catch (e) {
            console.error("Erreur lors de la lecture des données d'édition:", e);
        } finally {
            sessionStorage.removeItem('editReservationData');
        }
    }

    const tooltip = document.getElementById('reservation-tooltip');
    let hideTooltipTimeout;

    const showTooltip = async (block) => {
		clearTimeout(hideTooltipTimeout);
		const groupeId = block.dataset.groupeId;
		if (!groupeId || (tooltip.classList.contains('visible') && tooltip.dataset.currentGroupeId === groupeId)) {
			return;
		}
		tooltip.dataset.currentGroupeId = groupeId;

		try {
			const response = await fetch(`/api/reservation_details/${groupeId}`);
			if (!response.ok) throw new Error(`Erreur serveur: ${response.status}`);
			
			const details = await response.json();
			const isAdmin = document.body.dataset.isAdmin === 'true';
			const currentUserId = document.body.dataset.userId;
			const isMine = details.utilisateur_id.toString() === currentUserId;

			// === LOGIQUE D'AFFICHAGE FINALE AVEC SOUS-NIVEAUX ===
			let listItems = '';
			const kits = details.kits || {};
			const objetsManuels = details.objets_manuels || [];
			const hasKits = Object.keys(kits).length > 0;
			const hasObjetsManuels = objetsManuels.length > 0;

			if (hasKits) {
				listItems += `<li><strong>Kits :</strong></li>`;
				// On crée une sous-liste pour les kits
				listItems += `<ul style="margin-top: 5px; margin-bottom: 10px;">`;
				for (const kitId in kits) {
					listItems += `<li>${kits[kitId].quantite} x ${kits[kitId].nom}</li>`;
				}
				listItems += `</ul>`;
			}

			if (hasObjetsManuels) {
				listItems += `<li><strong>Matériel :</strong></li>`;
				// On crée une sous-liste pour le matériel
				listItems += `<ul style="margin-top: 5px;">`;
				objetsManuels.forEach(item => {
					listItems += `<li>${item.quantite_reservee} x ${item.nom}</li>`;
				});
				listItems += `</ul>`;
			}
			// =======================================================

			let buttonsHtml = '';
			if (isMine || isAdmin) {
				const pathParts = window.location.pathname.split('/');
				const currentDateStr = pathParts[pathParts.length - 1];
				buttonsHtml += `<button class="btn-edit-resa" data-groupe-id="${groupeId}" data-date="${currentDateStr}">Modifier</button>`;
				buttonsHtml += `<button class="btn-delete-resa" data-groupe-id="${groupeId}">Supprimer</button>`;
			}

			tooltip.innerHTML = `
				<div class="tooltip-header">
					<span class="tooltip-title">Réservation de <strong>${details.nom_utilisateur}</strong></span>
					<div class="tooltip-buttons">${buttonsHtml}</div>
				</div>
				<ul class="tooltip-list">${listItems || '<li>Aucun matériel spécifique.</li>'}</ul>`;

		} catch (error) {
			console.error("Erreur lors de la récupération des détails:", error);
			tooltip.innerHTML = `<div class="tooltip-header"><span class="tooltip-title">Erreur de chargement</span></div>`;
			return;
		}

		// Le reste de la fonction pour positionner la tooltip est correct et reste inchangé
		tooltip.className = 'tooltip';
		const tooltipRect = tooltip.getBoundingClientRect();
		const blockRect = block.getBoundingClientRect();
		const margin = 12;

		if ((window.innerHeight - blockRect.bottom) > tooltipRect.height + margin) {
			tooltip.classList.add('tooltip-on-bottom');
			tooltip.style.top = `${blockRect.bottom + margin}px`;
		} else {
			tooltip.classList.add('tooltip-on-top');
			tooltip.style.top = `${blockRect.top - tooltipRect.height - margin}px`;
		}
		let leftPos = blockRect.left + (blockRect.width / 2) - (tooltipRect.width / 2);
		if (leftPos < 10) leftPos = 10;
		if (leftPos + tooltipRect.width > window.innerWidth - 10) leftPos = window.innerWidth - tooltipRect.width - 10;
		tooltip.style.left = `${leftPos}px`;

		tooltip.classList.add('visible');
	};

    const startHideTooltipTimer = () => {
        hideTooltipTimeout = setTimeout(() => {
            tooltip.classList.remove('visible');
        }, 300);
    };

    // CORRECTION 2: On attache les écouteurs au nouveau conteneur
    scheduleContainer.addEventListener('mouseover', (e) => {
        // CORRECTION 3: On cible la nouvelle classe .event-block
        const block = e.target.closest('.event-block');
        if (block) {
            showTooltip(block);
        }
    });

    scheduleContainer.addEventListener('mouseout', (e) => {
        const block = e.target.closest('.event-block');
        if (block) {
            startHideTooltipTimer();
        }
    });

    tooltip.addEventListener('mouseover', () => clearTimeout(hideTooltipTimeout));
    tooltip.addEventListener('mouseout', startHideTooltipTimer);

    tooltip.addEventListener('click', (e) => {
        const editBtn = e.target.closest('.btn-edit-resa');
        if (editBtn) {
            tooltip.classList.remove('visible');
            if (typeof openReservationModal === 'function') {
                openReservationModal(editBtn.dataset.date, editBtn.dataset.groupeId);
            }
        }

        const deleteBtn = e.target.closest('.btn-delete-resa');
        if (deleteBtn) {
            const groupeId = deleteBtn.dataset.groupeId;
            const modal = document.getElementById('delete-reservation-modal');
            if (modal) {
                const confirmBtn = modal.querySelector('#confirm-delete-resa-btn');
                const newConfirmBtn = confirmBtn.cloneNode(true);
                confirmBtn.parentNode.replaceChild(newConfirmBtn, confirmBtn);

                newConfirmBtn.onclick = async () => {
					try {
						const csrfToken = document.querySelector('meta[name="csrf-token"]').getAttribute('content');
						const response = await fetch('/api/supprimer_reservation', {
							method: 'POST',
							headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
							body: JSON.stringify({ groupe_id: groupeId })
						});
                        const result = await response.json();
                        if (result.success) {
                            window.location.reload();
                        } else {
                            showInfoModal("Erreur de Suppression", result.error);
                        }
                    } catch (error) {
                        showInfoModal("Erreur de Communication", "Une erreur de communication est survenue.");
                    }
                };
                modal.style.display = 'flex';
                tooltip.classList.remove('visible');
            }
        }
    });

    const newReservationBtn = document.getElementById('new-reservation-btn');
    if (newReservationBtn) {
        const pathParts = window.location.pathname.split('/');
        const dateStr = pathParts[pathParts.length - 1];
        newReservationBtn.addEventListener('click', () => {
            if (typeof openReservationModal === 'function') {
                openReservationModal(dateStr);
            }
        });
    }
});