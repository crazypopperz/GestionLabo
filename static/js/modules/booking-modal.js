// =================================================================
// MODULE: BOOKING MODAL (Version Finale, Corrigée et Fiabilisée)
// =================================================================

function updateCartIcon() {
    const cart = JSON.parse(sessionStorage.getItem('reservationCart')) || {};
    const count = Object.keys(cart).length;
    const badge = document.getElementById('cart-count-badge');
    if (badge) {
        badge.textContent = count;
        badge.style.display = count > 0 ? 'flex' : 'none';
    }
}

async function openReservationModal(dateStr, groupIdToEdit = null) {
    const reservationModal = document.getElementById('reservation-modal');
    if (!reservationModal) return;

    // --- ÉTAT LOCAL DE LA MODALE (réinitialisé à chaque ouverture) ---
    let reservationCart = {};
    let kitCart = {};
    let reservationData = {};
    let selectedDateStr = dateStr;
    let editingGroupId = groupIdToEdit;
    let editingCartKey = null;

    // --- GESTION DU CONTEXTE (Nouvelle / Modification) ---
    const editDataJSON = sessionStorage.getItem('editReservationData');
    if (editDataJSON) {
        try {
            const editData = JSON.parse(editDataJSON);
            if (editData.date === dateStr) {
                editingCartKey = editData.editingCartKey;
                kitCart = editData.kits || {};
                reservationCart = editData.objets || {};
            }
        } catch (e) {
            console.error("Erreur de lecture des données d'édition:", e);
        } finally {
            sessionStorage.removeItem('editReservationData');
        }
    }

    // --- FONCTIONS INTERNES (inchangées) ---
    function findObjectData(objetId) {
        for (const categorie in reservationData.objets) {
            const found = reservationData.objets[categorie].find(o => o.id == objetId);
            if (found) return found;
        }
        return null;
    }

    function renderKits() {
        const kitsListContainer = document.getElementById('kits-list');
        if (!kitsListContainer) return;
        kitsListContainer.innerHTML = '';
        if (!reservationData.kits || reservationData.kits.length === 0) {
            kitsListContainer.innerHTML = '<p class="text-discret">Aucun kit disponible.</p>';
            return;
        }
        reservationData.kits.forEach(kit => {
            const itemHtml = `
                <div class="kit-item">
                    <div class="kit-item-header">
                        <span>${kit.nom}</span>
                        <span class="kit-availability">(${kit.disponibilite} dispo)</span>
                    </div>
                    <div class="kit-item-description">${kit.description || ''}</div>
                    <div class="kit-item-actions">
                        <span>Quantité :</span>
                        <div class="quantity-stepper" data-id="${kit.id}" data-type="kit">
                            <button class="quantity-btn" data-action="minus" aria-label="Diminuer la quantité">-</button>
                            <span class="quantity-value">${kitCart[kit.id]?.quantite || 0}</span>
                            <button class="quantity-btn" data-action="plus" aria-label="Augmenter la quantité">+</button>
                        </div>
                    </div>
                </div>`;
            kitsListContainer.innerHTML += itemHtml;
        });
    }

    function renderCategories() {
        const categoriesSidebar = document.getElementById('modal-categories-sidebar');
        if (!categoriesSidebar) return;
        categoriesSidebar.innerHTML = '';
        const categoryNames = Object.keys(reservationData.objets);
        if (categoryNames.length === 0) {
            categoriesSidebar.innerHTML = '<p style="padding:15px;">Aucun matériel disponible.</p>';
            return;
        }
        categoryNames.forEach((categorie, index) => {
            const button = document.createElement('button');
            button.className = 'category-button';
            button.dataset.categorieTarget = `category-group-${index}`;
            button.textContent = categorie;
            button.addEventListener('click', (e) => {
                document.querySelectorAll('.category-button').forEach(btn => btn.classList.remove('active'));
                e.currentTarget.classList.add('active');
                document.querySelectorAll('.category-object-group').forEach(group => group.style.display = 'none');
                document.getElementById(e.currentTarget.dataset.categorieTarget).style.display = 'block';
                filterObjectsList();
            });
            categoriesSidebar.appendChild(button);
        });
    }

    function renderAllObjects() {
        const reservationObjectsList = document.getElementById('reservation-objects-list');
        if (!reservationObjectsList) return;
        reservationObjectsList.innerHTML = '';
        const categoryNames = Object.keys(reservationData.objets);
        categoryNames.forEach((categorie, index) => {
            const objets = reservationData.objets[categorie];
            if (objets && objets.length > 0) {
                const groupContainer = document.createElement('div');
                groupContainer.id = `category-group-${index}`;
                groupContainer.className = 'category-object-group';
                groupContainer.style.display = 'none';
                objets.forEach(objet => {
                    const itemHtml = `
                        <div class="reservation-item" data-nom="${objet.nom.toLowerCase()}">
                            <div class="reservation-info">
                                <span class="reservation-nom">${objet.nom}</span>
                                <span class="reservation-dispo">Disponible : ${objet.quantite_disponible} / ${objet.quantite_totale}</span>
                            </div>
                            <div class="reservation-input">
                                <div class="quantity-stepper" data-id="${objet.id}" data-type="objet" data-nom="${objet.nom}">
                                    <button class="quantity-btn" data-action="minus" aria-label="Diminuer la quantité">-</button>
                                    <span class="quantity-value">${reservationCart[objet.id]?.quantite || 0}</span>
                                    <button class="quantity-btn" data-action="plus" aria-label="Augmenter la quantité">+</button>
                                </div>
                            </div>
                        </div>`;
                    groupContainer.innerHTML += itemHtml;
                });
                reservationObjectsList.appendChild(groupContainer);
            }
        });
        const categoriesSidebar = document.getElementById('modal-categories-sidebar');
        if(categoriesSidebar && categoriesSidebar.firstChild) {
            categoriesSidebar.firstChild.click();
        }
    }

    function updateAllSteppers() {
        const reservedByKits = {};
        for (const kitId in kitCart) {
            const kit = reservationData.kits.find(k => k.id == kitId);
            if (kit) {
                kit.objets.forEach(objInKit => {
                    reservedByKits[objInKit.objet_id] = (reservedByKits[objInKit.objet_id] || 0) + (objInKit.quantite * kitCart[kitId].quantite);
                });
            }
        }
        document.querySelectorAll('.reservation-item').forEach(item => {
            const stepper = item.querySelector('.quantity-stepper');
            const objetId = stepper.dataset.id;
            const objetData = findObjectData(objetId);
            if (!objetData) return;
            const quantiteManuelle = reservationCart[objetId]?.quantite || 0;
            const quantiteReserveeParKits = reservedByKits[objetId] || 0;
            const stockRestant = objetData.quantite_disponible - quantiteReserveeParKits - quantiteManuelle;
            item.querySelector('.quantity-value').textContent = quantiteManuelle;
            item.querySelector('.reservation-dispo').textContent = `Disponible : ${stockRestant} / ${objetData.quantite_totale}`;
        });
        renderKits();
    }

    function filterObjectsList() {
        const searchTerm = document.getElementById('reservation-search-input').value.toLowerCase();
        document.querySelectorAll('.reservation-item').forEach(item => {
            const parentGroup = item.closest('.category-object-group');
            if (parentGroup.style.display !== 'none') {
                item.style.display = item.dataset.nom.includes(searchTerm) ? 'flex' : 'none';
            }
        });
    }

    function handleQuantityChange(e) {
        const button = e.target.closest('.quantity-btn');
        if (!button) return;
        const stepper = button.closest('.quantity-stepper');
        const id = stepper.dataset.id;
        const type = stepper.dataset.type;
        const action = button.dataset.action;

        if (type === 'objet') {
            const nom = stepper.dataset.nom;
            const objetData = findObjectData(id);
            const reservedByKits = Object.values(kitCart).reduce((total, kit) => {
                const kitInfo = reservationData.kits.find(k => k.id == kit.id);
                const objInKit = kitInfo?.objets.find(o => o.objet_id == id);
                return total + (objInKit ? objInKit.quantite * kit.quantite : 0);
            }, 0);
            const max = objetData.quantite_disponible - reservedByKits;
            let currentQuantity = reservationCart[id]?.quantite || 0;
            if (action === 'plus' && currentQuantity < max) currentQuantity++;
            else if (action === 'minus' && currentQuantity > 0) currentQuantity--;
            if (currentQuantity > 0) reservationCart[id] = { quantite: currentQuantity, nom: nom };
            else delete reservationCart[id];
        }

        if (type === 'kit') {
            const kit = reservationData.kits.find(k => k.id == id);
            let currentKitQuantity = kitCart[id]?.quantite || 0;
            if (action === 'plus') {
                if (currentKitQuantity < kit.disponibilite) currentKitQuantity++;
                else showInfoModal("Stock Insuffisant", `Le stock est insuffisant pour ajouter un autre kit '${kit.nom}'.`);
            } else if (action === 'minus' && currentKitQuantity > 0) {
                currentKitQuantity--;
            }
            if (currentKitQuantity > 0) kitCart[id] = { quantite: currentKitQuantity, nom: kit.nom };
            else delete kitCart[id];
        }
        updateAllSteppers();
    }

    async function handleModalSubmit() {
        if (Object.keys(reservationCart).length === 0 && Object.keys(kitCart).length === 0) {
            showInfoModal("Panier Vide", "Veuillez sélectionner au moins un objet ou un kit.");
            return;
        }
        const heureDebut = document.getElementById('heure_debut').value;
        const heureFin = document.getElementById('heure_fin').value;
        const payload = {
            date: selectedDateStr,
            heure_debut: heureDebut,
            heure_fin: heureFin,
            kits: kitCart,
            objets: reservationCart
        };
        if (editingGroupId) {
            payload.groupe_id = editingGroupId;
            try {
                const csrfToken = document.querySelector('meta[name="csrf-token"]').getAttribute('content');
                const response = await fetch('/api/modifier_reservation', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
                    body: JSON.stringify(payload)
                });
                const result = await response.json();
                if (result.success) {
                    reservationModal.style.display = 'none';
                    window.location.reload();
                } else {
                    showInfoModal("Erreur de modification", result.error);
                }
            } catch (error) {
                showInfoModal("Erreur de Communication", "Une erreur est survenue lors de la communication avec le serveur.");
            }
        } else {
            const creneauKey = editingCartKey || `${selectedDateStr}_${heureDebut}_${heureFin}`;
            let cart = JSON.parse(sessionStorage.getItem('reservationCart')) || {};
            cart[creneauKey] = payload;
            sessionStorage.setItem('reservationCart', JSON.stringify(cart));
            reservationModal.style.display = 'none';
            updateCartIcon();
            if (editingCartKey) {
                window.location.href = '/panier';
            }
        }
    }
    
    // --- INITIALISATION DE LA MODALE ---
    const localDate = new Date(dateStr + 'T00:00:00');
    const title = (editingGroupId || editingCartKey) ? "Modifier la réservation pour le" : "Réserver du matériel pour le";
    document.getElementById('reservation-modal-title').textContent = `${title} ${localDate.toLocaleDateString('fr-FR', {weekday: 'long', day: 'numeric', month: 'long'})}`;
    document.getElementById('reservation-search-input').value = '';
    reservationModal.style.display = 'flex';

    const response = await fetch(`/api/reservation_data/${dateStr}`);
    reservationData = await response.json();
    
    if (editingGroupId) {
        const detailsResponse = await fetch(`/api/reservation_details/${editingGroupId}`);
        const details = await detailsResponse.json();
        kitCart = details.kits || {};
        if (Array.isArray(details.objets_manuels)) {
            reservationCart = details.objets_manuels.reduce((acc, item) => {
                acc[item.objet_id] = { quantite: item.quantite_reservee, nom: item.nom };
                return acc;
            }, {});
        }
        document.getElementById('heure_debut').value = new Date(details.debut_reservation).toTimeString().slice(0, 5);
        document.getElementById('heure_fin').value = new Date(details.fin_reservation).toTimeString().slice(0, 5);
    }

    renderCategories();
    renderAllObjects();
    renderKits();
    updateAllSteppers();

    // === CORRECTION FINALE : GESTION DES ÉCOUTEURS D'ÉVÉNEMENTS ===
    const heureDebutSelect = document.getElementById('heure_debut');
    const heureFinSelect = document.getElementById('heure_fin');
    const addToCartBtn = document.getElementById('add-to-cart-btn');
    const reservationObjectsList = document.getElementById('reservation-objects-list');
    const kitsListContainer = document.getElementById('kits-list');
    const reservationSearchInput = document.getElementById('reservation-search-input');

    function updateHeureFin() {
        const heureDebutParts = heureDebutSelect.value.split(':');
        const heureDebutNum = parseInt(heureDebutParts[0], 10);
        const heureFinNum = heureDebutNum + 1;
        const heureFinStr = String(heureFinNum).padStart(2, '0') + ':00';
        if (heureFinSelect.querySelector(`option[value="${heureFinStr}"]`)) {
            heureFinSelect.value = heureFinStr;
        }
    }
    
    // On attache les écouteurs une seule fois en utilisant .on... qui écrase les précédents
    heureDebutSelect.onchange = updateHeureFin;
    addToCartBtn.onclick = handleModalSubmit;
    reservationObjectsList.onclick = handleQuantityChange;
    kitsListContainer.onclick = handleQuantityChange;
    reservationSearchInput.oninput = filterObjectsList;

    // On met à jour le texte du bouton et l'heure de fin
    addToCartBtn.textContent = editingGroupId ? "Valider la modification" : (editingCartKey ? "Mettre à jour le panier" : "Ajouter au panier");
    if (!editingGroupId && !editingCartKey) {
        updateHeureFin();
    }
}

// --- DÉMARRAGE ---
document.addEventListener("DOMContentLoaded", function () {
    updateCartIcon();

    const editDataJSON = sessionStorage.getItem('editReservationData');
    if (editDataJSON) {
        try {
            const editData = JSON.parse(editDataJSON);
            const pathDate = window.location.pathname.split('/').pop();
            if (editData.date === pathDate && editData.editingCartKey) {
                openReservationModal(editData.date);
            }
        } catch (e) {
            console.error("Erreur de lecture des données d'édition:", e);
            sessionStorage.removeItem('editReservationData');
        }
    }
});