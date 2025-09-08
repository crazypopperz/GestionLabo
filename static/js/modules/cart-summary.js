// =================================================================
// MODULE: CART SUMMARY (Version Finale et Corrigée)
// =================================================================
document.addEventListener("DOMContentLoaded", function () {
    const cartListContainer = document.getElementById('cart-summary-list');
    const cartActions = document.getElementById('cart-actions');
    if (!cartListContainer) return;

    function renderCart() {
        const cart = JSON.parse(sessionStorage.getItem('reservationCart')) || {};
        const cartKeys = Object.keys(cart);

        cartListContainer.innerHTML = '';

        if (cartKeys.length === 0) {
            cartListContainer.innerHTML = '<p style="text-align: center; padding: 20px; color: #6c7a89;">Votre panier est vide.</p>';
            cartActions.style.display = 'none';
            return;
        }

        cartActions.style.display = 'flex';

        // Trier les clés pour un affichage chronologique
        cartKeys.sort((a, b) => {
            const dateA = new Date(cart[a].date + 'T' + cart[a].heure_debut);
            const dateB = new Date(cart[b].date + 'T' + cart[b].heure_debut);
            return dateA - dateB;
        });

        cartKeys.forEach(key => {
            const item = cart[key];
            const localDate = new Date(item.date + 'T00:00:00');
            const dateText = localDate.toLocaleDateString('fr-FR', { weekday: 'long', day: 'numeric', month: 'long' });

            let objectsHtml = '';
            
            if (item.kits && Object.keys(item.kits).length > 0) {
                 objectsHtml += '<h4 class="summary-subtitle">Kits</h4><ul>';
                 for (const kitId in item.kits) {
                     const kitData = item.kits[kitId];
                     if (kitData && kitData.quantite > 0) {
                        objectsHtml += `<li>${kitData.quantite} x <strong>${kitData.nom}</strong></li>`;
                     }
                 }
                 objectsHtml += '</ul>';
            }

            if (item.objets && Object.keys(item.objets).length > 0) {
                objectsHtml += '<h4 class="summary-subtitle">Matériel</h4><ul>';
                for (const objId in item.objets) {
                    objectsHtml += `<li>${item.objets[objId].quantite} x ${item.objets[objId].nom}</li>`;
                }
                objectsHtml += '</ul>';
            }

            const itemHtml = `
                <div class="summary-item" data-id="${key}">
                    <div class="summary-item-details">
                        <p><strong>Le ${dateText} de ${item.heure_debut} à ${item.heure_fin}</strong></p>
                        ${objectsHtml}
                    </div>
                    <div class="summary-actions">
                        <button class="btn-action btn-secondary btn-edit-cart-item" data-id="${key}">Modifier</button>
                        <button class="btn-action btn-danger btn-remove-cart-item" data-id="${key}">Supprimer</button>
                    </div>
                </div>
            `;
            cartListContainer.innerHTML += itemHtml;
        });
    }

    renderCart();

    cartActions.addEventListener('click', async (e) => {
        if (e.target.id === 'clear-cart-btn') {
            const modal = document.getElementById('clear-cart-modal');
            if (modal) {
                modal.style.display = 'flex';
            }
        }
        
        if (e.target.id === 'confirm-cart-btn') {
            const cart = JSON.parse(sessionStorage.getItem('reservationCart')) || {};
            if (Object.keys(cart).length === 0) {
                showInfoModal("Panier Vide", "Votre panier est vide.");
                return;
            }

            try {
                const csrfToken = document.querySelector('meta[name="csrf-token"]').getAttribute('content');
                const response = await fetch('/api/valider_panier', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': csrfToken
                    },
                    body: JSON.stringify(cart)
                });
                const result = await response.json();
                if (result.success) {
                    sessionStorage.removeItem('reservationCart');
                    // Rediriger vers le calendrier pour voir le résultat
                    window.location.href = '/calendrier'; 
                } else {
                    showInfoModal("Erreur de Réservation", result.error);
                }
            } catch (error) {
                console.error("Erreur validation panier:", error);
                showInfoModal("Erreur de Communication", "Une erreur de communication est survenue.");
            }
        }
    });

    cartListContainer.addEventListener('click', (e) => {
        const removeBtn = e.target.closest('.btn-remove-cart-item');
        const editBtn = e.target.closest('.btn-edit-cart-item');

        if (removeBtn) {
            const keyToRemove = removeBtn.dataset.id;
            const modal = document.getElementById('danger-modal'); // Utilisation d'une modale de danger générique
            if (modal) {
                modal.querySelector('#danger-modal-text').textContent = "Êtes-vous sûr de vouloir retirer cette réservation de votre panier ?";
                modal.style.display = 'flex';
                
                const confirmBtn = modal.querySelector('#danger-modal-confirm-btn');
                // Cloner pour éviter les écouteurs multiples
                const newConfirmBtn = confirmBtn.cloneNode(true);
                confirmBtn.parentNode.replaceChild(newConfirmBtn, confirmBtn);

                newConfirmBtn.addEventListener('click', () => {
                    let cart = JSON.parse(sessionStorage.getItem('reservationCart')) || {};
                    delete cart[keyToRemove];
                    sessionStorage.setItem('reservationCart', JSON.stringify(cart));
                    renderCart();
                    if (typeof updateCartIcon === 'function') updateCartIcon();
                    modal.style.display = 'none';
                });
            }
        }

        if (editBtn) {
            const keyToEdit = editBtn.dataset.id;
            let cart = JSON.parse(sessionStorage.getItem('reservationCart')) || {};
            const itemToEdit = cart[keyToEdit];

            if (itemToEdit) {
                // On ne supprime plus l'item du panier immédiatement
                // On passe les données à la page suivante via sessionStorage pour l'édition
                const editData = {
                    ...itemToEdit,
                    editingCartKey: keyToEdit // On passe la clé pour savoir quelle entrée remplacer
                };
                sessionStorage.setItem('editReservationData', JSON.stringify(editData));
                window.location.href = `/jour/${itemToEdit.date}`;
            }
        }
    });

    const confirmClearCartBtn = document.getElementById('confirm-clear-cart-btn');
    if (confirmClearCartBtn) {
        confirmClearCartBtn.addEventListener('click', () => {
            sessionStorage.removeItem('reservationCart');
            renderCart();
            if (typeof updateCartIcon === 'function') updateCartIcon();
            const modal = document.getElementById('clear-cart-modal');
            if (modal) {
                modal.style.display = 'none';
            }
        });
    }
});