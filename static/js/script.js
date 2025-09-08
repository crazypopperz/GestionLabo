// =================================================================
// FONCTION GLOBALE POUR AFFICHER LA MODALE D'INFORMATION
// Doit être déclarée ici pour être accessible par les autres modules JS.
// =================================================================
function showInfoModal(title, message) {
    const modal = document.getElementById('info-modal');
    if (modal) {
        const modalTitle = document.getElementById('info-modal-title');
        const modalText = document.getElementById('info-modal-text');
        
        if (modalTitle && modalText) {
            modalTitle.querySelector('span').textContent = title;
            modalText.textContent = message;
            modal.style.display = 'flex';
        }
    }
}

document.addEventListener("DOMContentLoaded", function () {

    // =================================================================
	// SECTION 1 : LOGIQUE DE TRI ET PAGINATION DYNAMIQUE (UNIFIÉE)
	// =================================================================
	const dynamicContent = document.getElementById('dynamic-content');
	if (dynamicContent) {
		// On sélectionne les filtres seulement s'ils existent
		const searchInput = document.getElementById('search-input');
		const armoireFilter = document.getElementById('filtre-armoire');
		const categorieFilter = document.getElementById('filtre-categorie');
		const etatFilter = document.getElementById('filtre-etat');
		let searchTimeout;

		function fetchDynamicContent(page = 1, sortBy = null, direction = null) {
			const currentSortBy = sortBy || dynamicContent.dataset.sortBy || 'nom';
			const currentDirection = direction || dynamicContent.dataset.direction || 'asc';
			const endpoint = dynamicContent.dataset.endpoint;
			const endpointId = dynamicContent.dataset.endpointId || '';

			const params = new URLSearchParams({
				page: page,
				sort_by: currentSortBy,
				direction: currentDirection
			});

			// Ajoute les filtres de la barre de recherche (uniquement s'ils existent)
			if (searchInput && searchInput.value) params.set('q', searchInput.value);
			if (armoireFilter && armoireFilter.value) params.set('armoire', armoireFilter.value);
			if (categorieFilter && categorieFilter.value) params.set('categorie', categorieFilter.value);
			if (etatFilter && etatFilter.value) params.set('etat', etatFilter.value);

			// Ajoute les filtres contextuels de la page (armoire ou catégorie)
			if (dynamicContent.dataset.armoireId) params.set('armoire', dynamicContent.dataset.armoireId);
			if (dynamicContent.dataset.categorieId) params.set('categorie', dynamicContent.dataset.categorieId);

			const apiUrl = `/api/${endpoint}/${endpointId}?${params.toString().replace(/\/$/, "")}`;

			fetch(apiUrl)
			.then(response => response.json())
			.then(data => {
				dynamicContent.innerHTML = data.html;
				dynamicContent.dataset.sortBy = currentSortBy;
				dynamicContent.dataset.direction = currentDirection;
			})
			.catch(error => {
				console.error("Erreur lors de la mise à jour du contenu:", error);
				dynamicContent.innerHTML = "<p>Erreur de chargement des données.</p>";
			});
		}

		function debounceFetch() {
			clearTimeout(searchTimeout);
			searchTimeout = setTimeout(() => fetchDynamicContent(1), 300);
		}

		if (searchInput) searchInput.addEventListener('input', debounceFetch);
		if (armoireFilter) armoireFilter.addEventListener('change', () => fetchDynamicContent(1));
		if (categorieFilter) categorieFilter.addEventListener('change', () => fetchDynamicContent(1));
		if (etatFilter) etatFilter.addEventListener('change', () => fetchDynamicContent(1));

		dynamicContent.addEventListener('click', function (e) {
			const pageLink = e.target.closest('.page-link');
			if (pageLink) {
				e.preventDefault();
				const url = new URL(pageLink.href);
				const page = url.searchParams.get('page');
				if (page) {
					fetchDynamicContent(page);
				}
			}
			
			const sortLink = e.target.closest('.sortable a');
			if (sortLink) {
				e.preventDefault();
				const url = new URL(sortLink.href);
				const sortBy = url.searchParams.get('sort_by');
				const direction = url.searchParams.get('direction');
				fetchDynamicContent(1, sortBy, direction);
			}
		});
	}

	// =================================================================
	// SECTION 2 : GESTION DES CASES À COCHER (Commande & Traité)
	// =================================================================
	// Cette logique est maintenant globale et s'applique à toutes les pages.
	const csrfTokenMeta = document.querySelector('meta[name="csrf-token"]');
	if (csrfTokenMeta) {
		const csrfToken = csrfTokenMeta.getAttribute('content');

		// Utilise la délégation d'événements pour une meilleure performance
		document.body.addEventListener('change', function(e) {
			
			// Gère la case "Mis en commande"
			if (e.target.matches('.commande-checkbox')) {
				const checkbox = e.target;
				fetch(`/maj_commande/${checkbox.dataset.id}`, {
					method: "POST",
					headers: {
						"Content-Type": "application/json",
						"X-CSRFToken": csrfToken
					},
					body: JSON.stringify({ en_commande: checkbox.checked })
				})
				.then(response => {
					if (!response.ok) { throw new Error('La réponse du serveur n\'est pas OK'); }
					return response.json();
				})
				.then(data => {
					if (data.success) {
						checkbox.closest('tr').classList.toggle('acquitte', checkbox.checked);
					} else {
						showInfoModal("Erreur", "Erreur de mise à jour.");
						checkbox.checked = !checkbox.checked; // Annule le changement en cas d'erreur
					}
				})
				.catch(error => {
					console.error('Erreur:', error);
					showInfoModal("Erreur de Communication", "Une erreur de communication est survenue.");
					checkbox.checked = !checkbox.checked;
				});
			}

			// Gère la case "Traité"
			if (e.target.matches('.traite-checkbox')) {
				const checkbox = e.target;
				fetch(`/api/maj_traite/${checkbox.dataset.id}`, {
					method: "POST",
					headers: {
						"Content-Type": "application/json",
						"X-CSRFToken": csrfToken
					},
					body: JSON.stringify({ traite: checkbox.checked })
				})
				.then(response => {
					if (!response.ok) { throw new Error('La réponse du serveur n\'est pas OK'); }
					return response.json();
				})
				.then(data => {
					if (data.success) {
						checkbox.closest('tr').classList.toggle('acquitte', checkbox.checked);
					} else {
						showInfoModal("Erreur", "Erreur de mise à jour.");
						checkbox.checked = !checkbox.checked;
					}
				})
				.catch(error => {
					console.error('Erreur:', error);
					showInfoModal("Erreur de Communication", "Une erreur de communication est survenue.");
					checkbox.checked = !checkbox.checked;
				});
			}
		});
	}

    // =================================================================
    // SECTION 3 : RECHERCHE GLOBALE DANS LE HEADER
    // =================================================================
    const globalSearchInput = document.getElementById("recherche-objet");
    const resultsContainer = document.getElementById("search-results-container");
    let searchTimeoutHeader;

    if (globalSearchInput && resultsContainer) {
        globalSearchInput.addEventListener("input", function () {
            const query = this.value.trim();

            clearTimeout(searchTimeoutHeader);
            resultsContainer.innerHTML = '';
            resultsContainer.style.display = 'none';

            if (query.length < 2) {
                return;
            }

            searchTimeoutHeader = setTimeout(() => {
                fetch(`/api/rechercher?q=${encodeURIComponent(query)}`)
                .then(response => response.json())
                .then(data => {
                    resultsContainer.innerHTML = '';
                    if (data.length > 0) {
                        const list = document.createElement('ul');
                        list.className = 'search-results-list';
                        data.forEach(item => {
                            const li = document.createElement('li');
                            const a = document.createElement('a');
                            a.href = `/objet/${item.id}`;

                            const nameSpan = document.createElement('span');
                            nameSpan.textContent = item.nom;

                            const contextSmall = document.createElement('small');
                            contextSmall.className = 'search-result-context';
                            contextSmall.textContent = `Armoire: ${item.armoire_nom} / Catégorie: ${item.categorie_nom}`;

                            a.appendChild(nameSpan);
                            a.appendChild(contextSmall);
                            li.appendChild(a);
                            list.appendChild(li);
                        });
                        resultsContainer.appendChild(list);
                        resultsContainer.style.display = 'block';
                    } else {
                        resultsContainer.innerHTML = '<div style="padding: 10px; color: #6c7a89;">Aucun résultat trouvé.</div>';
                        resultsContainer.style.display = 'block';
                    }
                })
                .catch(error => {
                    console.error("Erreur de recherche:", error)
                    resultsContainer.innerHTML = '<div style="padding: 10px; color: #dc3545;">Erreur de recherche.</div>';
                    resultsContainer.style.display = 'block';
                });
            }, 300);
        });

        document.addEventListener('click', function (event) {
            if (!globalSearchInput.contains(event.target)) {
                resultsContainer.style.display = 'none';
            }
        });
    }

    const urlParams = new URLSearchParams(window.location.search);
    const highlightId = urlParams.get('highlight');
    if (highlightId) {
        setTimeout(() => {
            const targetRow = document.querySelector(`tr[data-objet-id="${highlightId}"]`);
            if (targetRow) {
                targetRow.scrollIntoView({
                    behavior: 'smooth',
                    block: 'center'
                });
                targetRow.classList.add('highlight');
                setTimeout(() => {
                    targetRow.classList.remove('highlight');
                }, 3000);
            }
        }, 100);
    }

    // =================================================================
    // SECTION 4 : ÉDITION DES CARTES (Pages de gestion)
    // =================================================================
    document.querySelectorAll('.edit-btn').forEach(button => {
        button.addEventListener('click', function () {
            const card = this.closest('.item-card');
            card.querySelector('.card-info').style.display = 'none';
            card.querySelector('.card-actions').style.display = 'none';
            card.querySelector('.edit-mode').style.display = 'flex';
            card.querySelector('.edit-input').focus();
        });
    });

    document.querySelectorAll('.save-btn').forEach(button => {
        button.addEventListener('click', function () {
            const card = this.closest('.item-card');
            const input = card.querySelector('.edit-input');
            const csrfToken = document.querySelector('meta[name="csrf-token"]').getAttribute('content');

            const isArmoiresPage = window.location.pathname.includes('gestion_armoires');
            const fetchURL = isArmoiresPage ? '/modifier_armoire' : '/modifier_categorie';

            fetch(fetchURL, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrfToken
                },
                body: JSON.stringify({
                    id: this.dataset.id,
                    nom: input.value
                })
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    card.querySelector('.card-title').textContent = data.nouveau_nom;
                    card.querySelector('.cancel-btn').click();
                } else {
                    showInfoModal('Erreur', data.error);
                }
            });
        });
    });

    document.querySelectorAll('.cancel-btn').forEach(button => {
        button.addEventListener('click', function() {
            const card = this.closest('.item-card');
            card.querySelector('.edit-mode').style.display = 'none';
            card.querySelector('.card-info').style.display = '';
            card.querySelector('.card-actions').style.display = '';
            card.querySelector('.edit-input').value = card.querySelector('.card-title').textContent.trim();
        });
    });


    // =================================================================
    // SECTION 5 : GESTION DES MODALES ET ACTIONS (UNIFIÉE ET CORRIGÉE)
    // =================================================================
    document.addEventListener('click', function (e) {

        const closeBtn = e.target.closest('.modal-overlay .close-btn, .modal-overlay .btn-cancel');
        const overlay = e.target.closest('.modal-overlay');
        if (closeBtn || (overlay && e.target === overlay)) {
            const modalToClose = e.target.closest('.modal-overlay');
            if (modalToClose) {
                modalToClose.style.display = 'none';
            }
            return;
        }

        const trigger = e.target.closest('[data-modal-trigger]');
        if (trigger) {
            const modalId = trigger.dataset.modalTrigger;
            const modal = document.getElementById(modalId);
            if (!modal) {
                console.error(`Modale non trouvée avec l'ID : ${modalId}`);
                return;
            }
            modal.style.display = 'flex';

            const form = modal.querySelector('form');
            if (form) {
                if (trigger.dataset.actionUrl) {
                    form.action = trigger.dataset.actionUrl;
                }
            }
            
            if (modalId === 'cloture-impossible-modal') {
                const anneeScolaire = trigger.dataset.anneeScolaire;
                const anneeFin = trigger.dataset.anneeFin;
                modal.querySelector('#cloture-impossible-annee').textContent = anneeScolaire;
                modal.querySelector('#cloture-impossible-date').textContent = `le 01/06/${anneeFin}`;
            }

            if (modalId === 'add-object-modal') {
                const modalTitle = modal.querySelector('#modal-objet-title');
                const modalSubmitBtn = modal.querySelector('#modal-submit-btn');
                const imagePreviewContainer = modal.querySelector('#image-preview-container');
                const iconTemplate = document.getElementById('modal-icon-template');

                if (trigger.dataset.objetId) {
                    modalTitle.innerHTML = '';
                    if (iconTemplate) {
                        modalTitle.appendChild(iconTemplate.cloneNode(true));
                    }
                    modalTitle.appendChild(document.createTextNode(" Modifier l'objet"));
                    modalSubmitBtn.textContent = "Mettre à jour";
                    form.action = `/modifier_objet/${trigger.dataset.objetId}`;
                    form.querySelector('#nom').value = trigger.dataset.nom || '';
                    form.querySelector('#quantite').value = trigger.dataset.quantite || '';
                    form.querySelector('#seuil').value = trigger.dataset.seuil || '';
                    form.querySelector('#date_peremption').value = trigger.dataset.datePeremption || '';
                    form.querySelector('#armoire_id').value = trigger.dataset.armoireId || '';
                    form.querySelector('#categorie_id').value = trigger.dataset.categorieId || '';
                    const imageUrl = trigger.dataset.imageUrl;
                    if (imageUrl) {
                        imagePreviewContainer.querySelector('img').src = imageUrl;
                        imagePreviewContainer.style.display = 'block';
                    } else {
                        imagePreviewContainer.style.display = 'none';
                    }
                    form.querySelector('#supprimer_image').checked = false;
                } else {
                    modalTitle.innerHTML = '';
                    if (iconTemplate) {
                        modalTitle.appendChild(iconTemplate.cloneNode(true));
                    }
                    modalTitle.appendChild(document.createTextNode(" Ajouter un nouvel objet"));
                    modalSubmitBtn.textContent = "Enregistrer l'objet";
                    form.action = document.body.dataset.addUrl;
                    form.reset();
                    imagePreviewContainer.style.display = 'none';
                    modal.querySelectorAll('.file-msg').forEach(msgSpan => {
                        const dropZone = msgSpan.closest('.file-drop-zone');
                        if (dropZone) {
                            const input = dropZone.querySelector('.file-input');
                            input.value = '';
                            msgSpan.textContent = dropZone.dataset.defaultMsg || 'Glissez-déposez ou cliquez pour choisir un fichier';
                        }
                    });
                }
            }

            if (trigger.dataset.formUsername) {
                modal.querySelectorAll('#username, #username-placeholder, #username-to-match').forEach(el => {
                    el.textContent = trigger.dataset.formUsername;
                });
            }
            if (modalId === 'edit-email-modal' && trigger.dataset.formEmail) {
                form.querySelector('#email').value = trigger.dataset.formEmail;
            }
            if (modalId === 'edit-fournisseur-modal') {
                form.querySelector('#edit_nom').value = trigger.dataset.formNom || '';
                form.querySelector('#edit_site_web').value = trigger.dataset.formSite_web || '';
            }
            if (modalId === 'delete-user-modal') {
                const username = trigger.dataset.formUsername;
                form.dataset.username = username; // Stocke le nom exact
                modal.querySelector('#username-to-match').textContent = username;
                modal.querySelector('#username-placeholder').textContent = username;
                modal.querySelector('#delete-confirm-input').value = '';
                modal.querySelector('#delete-error-message').textContent = '';
            }
            if (modalId === 'budget-modal') {
                form.querySelector('#annee').value = trigger.dataset.formAnnee || new Date().getFullYear();
                form.querySelector('#montant_initial').value = trigger.dataset.formMontantInitial || '0.00';
            }
            if (modalId === 'edit-depense-modal') {
                const depenseId = trigger.dataset.depenseId;
                form.action = `/budget/modifier_depense/${depenseId}`;
                form.querySelector('#edit_date_depense').value = trigger.dataset.formDateDepense;
                form.querySelector('#edit_fournisseur_id').value = trigger.dataset.formFournisseurId;
                form.querySelector('#edit_contenu').value = trigger.dataset.formContenu;
                form.querySelector('#edit_montant').value = trigger.dataset.formMontant;
                const estBonAchatCheckbox = form.querySelector('#edit_est_bon_achat');
                estBonAchatCheckbox.checked = trigger.dataset.formEstBonAchat == '1';
                estBonAchatCheckbox.dispatchEvent(new Event('change'));
            }
            if (modalId === 'echeance-modal') {
                const modalTitle = modal.querySelector('#echeance-modal-title');
                const submitBtn = modal.querySelector('#echeance-submit-btn');
                const traiteGroup = modal.querySelector('#traite-group');
                const echeanceId = trigger.dataset.echeanceId;
                if (echeanceId) {
                    modalTitle.textContent = "Modifier une échéance";
                    submitBtn.textContent = "Enregistrer les modifications";
                    form.action = `/admin/echeances/modifier/${echeanceId}`;
                    form.querySelector('#intitule').value = trigger.dataset.formIntitule;
                    form.querySelector('#date_echeance').value = trigger.dataset.formDateEcheance;
                    form.querySelector('#details').value = trigger.dataset.formDetails;
                    traiteGroup.style.display = 'flex';
                    form.querySelector('#traite').checked = trigger.dataset.formTraite == '1';
                } else {
                    modalTitle.textContent = "Ajouter une échéance";
                    submitBtn.textContent = "Enregistrer";
                    form.action = document.body.dataset.urlAjoutEcheance;
                    form.reset();
                    traiteGroup.style.display = 'none';
                }
            }
            if (modalId === 'reset-licence-modal') {
                const passwordInput = modal.querySelector('#admin_password_confirm');
                if (passwordInput) {
                    passwordInput.value = '';
                }
            }
        }

        const suggestBtn = e.target.closest('.btn-suggest');
        if (suggestBtn) {
            (async() => {
                const objetId = suggestBtn.dataset.objetId;
                const objetNom = suggestBtn.dataset.objetNom;
                const modal = document.getElementById('suggestion-modal');
                if (!modal)
                    return;
                try {
                    const response = await fetch(`/api/suggestion_commande/${objetId}`);
                    if (!response.ok)
                        throw new Error("Erreur du serveur.");
                    const data = await response.json();
                    modal.querySelector('#suggestion-modal-title').textContent = `Suggestion pour "${objetNom}"`;
                    modal.querySelector('#suggestion-details').innerHTML =
                        `Consommation sur les 90 derniers jours : <strong>${data.consommation} unités</strong>.<br>` + 
`Suggestion de commande (avec marge) : <strong>${data.suggestion} unités</strong>.`;
                    const quantityInput = modal.querySelector('#suggestion-quantity-input');
                    quantityInput.value = data.suggestion;
                    modal.style.display = 'flex';
                    const confirmBtn = modal.querySelector('#suggestion-confirm-btn');
                    confirmBtn.onclick = () => {
                        const quantiteACommander = quantityInput.value;
                        if (quantiteACommander && quantiteACommander > 0) {
                            console.log(`L'utilisateur a confirmé vouloir commander ${quantiteACommander} unité(s) de "${objetNom}".`);
                            modal.style.display = 'none';
                        } else {
                            showInfoModal("Quantité Invalide", "Veuillez entrer une quantité valide.");
                        }
                    };
                } catch (error) {
                    console.error("Erreur lors de la suggestion de commande:", error);
                    showInfoModal("Erreur", "Impossible d'obtenir une suggestion pour le moment.");
                }
            })();
        }
    });

    // =================================================================
    // SECTION 6 : DISPARITION AUTOMATIQUE DES MESSAGES FLASH
    // =================================================================
    document.querySelectorAll('.flash').forEach(function (flashMessage) {
        setTimeout(() => {
            flashMessage.style.opacity = '0';
            flashMessage.style.transform = 'translateY(-20px)';
            flashMessage.style.margin = '0';
            flashMessage.style.padding = '0';
            setTimeout(() => {
                flashMessage.remove();
            }, 500);
        }, 1000);
    });

	// =================================================================
	// SECTION 7 : GESTION DU DÉPLACEMENT EN MASSE
	// =================================================================
	const selectAllCheckbox = document.getElementById('select-all-checkbox');
	const objetCheckboxes = document.querySelectorAll('.objet-checkbox');
	const bulkActionSection = document.getElementById('bulk-action-section');
	if (selectAllCheckbox && objetCheckboxes.length > 0 && bulkActionSection) {
		const bulkMoveBtn = document.getElementById('bulk-move-btn');
		const moveDestination = document.getElementById('move-destination');
		function toggleBulkActionSection() {
			const anyChecked = document.querySelector('.objet-checkbox:checked');
			bulkActionSection.style.display = anyChecked ? 'flex' : 'none';
		}
		selectAllCheckbox.addEventListener('change', function () {
			objetCheckboxes.forEach(checkbox => {
				checkbox.checked = this.checked;
			});
			toggleBulkActionSection();
		});
		objetCheckboxes.forEach(checkbox => {
			checkbox.addEventListener('change', function () {
				if (!this.checked) {
					selectAllCheckbox.checked = false;
				}
				toggleBulkActionSection();
			});
		});
		bulkMoveBtn.addEventListener('click', function () {
			const selectedObjectIds = Array.from(objetCheckboxes).filter(cb => cb.checked).map(cb => cb.dataset.id);
			if (selectedObjectIds.length === 0) {
				showInfoModal("Aucune Sélection", "Veuillez sélectionner au moins un objet à déplacer.");
				return;
			}
			const destinationId = moveDestination.value;
			const pathname = window.location.pathname;
			const typeDestination = pathname.includes('/armoire/') ? 'armoire' : (pathname.includes('/categorie/') ? 'categorie' : '');
			if (!typeDestination) {
				showInfoModal("Action Impossible", "Action de déplacement non disponible sur cette page.");
				return;
			}

			// === CORRECTION : Ajout du token CSRF ===
			const csrfToken = document.querySelector('meta[name="csrf-token"]').getAttribute('content');

			fetch('/api/deplacer_objets', {
				method: 'POST',
				headers: {
					'Content-Type': 'application/json',
					'X-CSRFToken': csrfToken // <-- LA LIGNE MANQUANTE EST ICI
				},
				body: JSON.stringify({
					objet_ids: selectedObjectIds,
					destination_id: destinationId,
					type_destination: typeDestination
				})
			})
			.then(response => response.json())
			.then(data => {
				if (data.success) {
					window.location.reload();
				} else {
					showInfoModal("Erreur", "Erreur lors du déplacement des objets : " + (data.error || 'Erreur inconnue'));
				}
			})
			.catch(error => { // Ajout d'un .catch pour mieux gérer les erreurs réseau
				console.error("Erreur lors du déplacement en masse :", error);
				showInfoModal("Erreur de Communication", "Une erreur est survenue lors de la communication avec le serveur.");
			});
		});
	}

    // =================================================================
    // SECTION 9 : FILTRE SUR LA PAGE DE MODIFICATION D'UN KIT
    // =================================================================
    const kitObjetSearch = document.getElementById('kit-objet-search');
    if (kitObjetSearch) {
        const availableObjectsTable = document.getElementById('available-objects-table');
        const rows = availableObjectsTable.querySelectorAll('tbody tr');

        kitObjetSearch.addEventListener('input', function () {
            const searchTerm = this.value.toLowerCase();
            rows.forEach(row => {
                const nomObjet = row.querySelector('td:first-child').textContent.toLowerCase();
                if (nomObjet.includes(searchTerm)) {
                    row.style.display = '';
                } else {
                    row.style.display = 'none';
                }
            });
        });
    }

    // =================================================================
    // SECTION 10 : LOGIQUE DE LA PAGE DE RAPPORTS
    // =================================================================
    const formRapportsGrid = document.querySelector('.form-rapports-grid');
    if (formRapportsGrid) {
        const dateDebutInput = formRapportsGrid.querySelector('#date_debut');
        const dateFinInput = formRapportsGrid.querySelector('#date_fin');

        const today = new Date().toISOString().split('T')[0];
        if (!dateFinInput.value) {
            dateFinInput.value = today;
        }

        dateDebutInput.addEventListener('change', () => {
            if (dateDebutInput.value) {
                dateFinInput.min = dateDebutInput.value;
                if (dateFinInput.value < dateDebutInput.value) {
                    dateFinInput.value = dateDebutInput.value;
                }
            }
        });
    }

    // =================================================================
    // SECTION 11 : GESTION DES ZONES DE DÉPÔT DE FICHIERS
    // =================================================================
    document.querySelectorAll('.file-drop-zone').forEach(dropZone => {
        const input = dropZone.querySelector('.file-input');
        const msgSpan = dropZone.querySelector('.file-msg');
        const defaultMsg = msgSpan.textContent;

        input.addEventListener('change', () => {
            if (input.files.length > 0) {
                msgSpan.textContent = input.files[0].name;
            } else {
                msgSpan.textContent = defaultMsg;
            }
        });

        dropZone.addEventListener('dragover', (e) => {
            e.preventDefault();
            dropZone.classList.add('is-dragover');
        });
        ['dragleave', 'dragend'].forEach(type => {
            dropZone.addEventListener(type, () => {
                dropZone.classList.remove('is-dragover');
            });
        });
        dropZone.addEventListener('drop', (e) => {
            e.preventDefault();
            dropZone.classList.remove('is-dragover');
            if (e.dataTransfer.files.length) {
                input.files = e.dataTransfer.files;
                const event = new Event('change', {
                    bubbles: true
                });
                input.dispatchEvent(event);
            }
        });
    });

    // =================================================================
    // SECTION 12 : MISE À JOUR DYNAMIQUE DES LIENS D'EXPORT (BUDGET)
    // =================================================================
    const dateDebutExport = document.getElementById('date_debut_export');
    const dateFinExport = document.getElementById('date_fin_export');
    const pdfLink = document.getElementById('export-pdf-link');
    const excelLink = document.getElementById('export-excel-link');

    if (dateDebutExport && dateFinExport && pdfLink && excelLink) {
        function updateExportLinks() {
            const dateDebut = dateDebutExport.value;
            const dateFin = dateFinExport.value;

            const exportUrl = '/budget/exporter';

            const paramsPdf = new URLSearchParams({
                format: 'pdf',
                date_debut: dateDebut,
                date_fin: dateFin
            });
            pdfLink.href = `${exportUrl}?${paramsPdf.toString()}`;

            const paramsExcel = new URLSearchParams({
                format: 'excel',
                date_debut: dateDebut,
                date_fin: dateFin
            });
            excelLink.href = `${exportUrl}?${paramsExcel.toString()}`;
        }

        dateDebutExport.addEventListener('change', updateExportLinks);
        dateFinExport.addEventListener('change', updateExportLinks);
        updateExportLinks();
    }

    // =================================================================
    // SECTION 13 : LOGIQUE POUR LA MODALE D'AJOUT DE DÉPENSE
    // =================================================================
    const depenseModal = document.getElementById('depense-modal');
    if (depenseModal) {
        const bonAchatCheckbox = depenseModal.querySelector('#est_bon_achat');
        const fournisseurSelect = depenseModal.querySelector('#fournisseur_id');

        bonAchatCheckbox.addEventListener('change', function () {
            if (this.checked) {
                fournisseurSelect.disabled = true;
                fournisseurSelect.value = '';
            } else {
                fournisseurSelect.disabled = false;
            }
        });
    }
    const editDepenseModal = document.getElementById('edit-depense-modal');
    if (editDepenseModal) {
        const bonAchatCheckbox = editDepenseModal.querySelector('#edit_est_bon_achat');
        const fournisseurSelect = editDepenseModal.querySelector('#edit_fournisseur_id');

        bonAchatCheckbox.addEventListener('change', function () {
            if (this.checked) {
                fournisseurSelect.disabled = true;
                fournisseurSelect.value = '';
            } else {
                fournisseurSelect.disabled = false;
            }
        });
    }

    // =================================================================
    // SECTION 14 : CONFIRMATION DE SUPPRESSION (UNIFIÉE)
    // =================================================================
    document.addEventListener('click', function (e) {
        // Logique pour les armoires/catégories
        const deleteInteractiveBtn = e.target.closest('.delete-form-interactive .delete-btn');
        if (deleteInteractiveBtn) {
            e.preventDefault();
            const form = deleteInteractiveBtn.closest('.delete-form-interactive');
            const itemName = form.dataset.itemName || 'cet élément';
            const itemType = form.dataset.itemType || 'élément';
            const modal = document.getElementById('danger-modal');
            if (!modal) return;
            const modalText = modal.querySelector('#danger-modal-text');
            modalText.textContent = `Êtes-vous sûr de vouloir supprimer ${itemType === 'armoire' ? "l'armoire" : "la catégorie"} "${itemName}" ? Cette action est définitive.`;
            modal.style.display = 'flex';
            const confirmBtn = modal.querySelector('#danger-modal-confirm-btn');
            
            // Nettoyage de l'ancien écouteur
            const newConfirmBtn = confirmBtn.cloneNode(true);
            confirmBtn.parentNode.replaceChild(newConfirmBtn, confirmBtn);

            newConfirmBtn.onclick = () => {
                form.submit();
            };
        }

        const deleteObjetBtn = e.target.closest('.btn-delete-objet');
        if (deleteObjetBtn) {
            e.preventDefault();
            const form = deleteObjetBtn.closest('form');
            const objetNom = deleteObjetBtn.dataset.objetNom;
            const modal = document.getElementById('danger-modal');
            if (!modal) return;
            
            const modalText = modal.querySelector('#danger-modal-text');
            modalText.innerHTML = `Êtes-vous sûr de vouloir supprimer l'objet <strong>'${objetNom}'</strong> ?<br>Cette action est irréversible.`;
            
            const confirmBtn = modal.querySelector('#danger-modal-confirm-btn');
            
            // Nettoyage de l'ancien écouteur
            const newConfirmBtn = confirmBtn.cloneNode(true);
            confirmBtn.parentNode.replaceChild(newConfirmBtn, confirmBtn);

            newConfirmBtn.onclick = () => {
                form.submit();
            };
            
            modal.style.display = 'flex';
        }
    });

    // =================================================================
    // SECTION 15 : COPIE DE L'ID D'INSTANCE
    // =================================================================
    const instanceIdCode = document.getElementById('instance-id-code');
    if (instanceIdCode) {
        instanceIdCode.addEventListener('click', function () {
            navigator.clipboard.writeText(this.textContent)
            .then(() => {
                const originalText = this.textContent;
                this.textContent = 'Copié !';
                setTimeout(() => {
                    this.textContent = originalText;
                }, 1500);
            })
            .catch(err => {
                console.error('Erreur de copie : ', err);
                showInfoModal("Erreur", "Impossible de copier l'identifiant.");
            });
        });
    }

    // =================================================================
    // SECTION 16 : GESTION DES ÉVÉNEMENTS DE LA PAGE ADMIN (Refactoring)
    // =================================================================
    const importDbInput = document.getElementById('fichier-db');
    if (importDbInput) {
        importDbInput.addEventListener('change', function () {
            if (this.files.length > 0) {
                this.form.submit();
            }
        });
    }

    const resetLicenceForm = document.getElementById('reset-licence-form');
    if (resetLicenceForm) {
        resetLicenceForm.addEventListener('submit', function (event) {
            const confirmation = confirm('Êtes-vous sûr de vouloir réinitialiser la licence ? L\'application repassera en mode GRATUIT limité à 50 objets.');
            if (!confirmation) {
                event.preventDefault();
            }
        });
    }

    // =================================================================
    // SECTION 16 : GESTION DES ÉVÉNEMENTS DE LA PAGE ADMIN (Refactoring)
    // ... (votre code existant pour importDbInput et resetLicenceForm) ...

    // NOUVEAU BLOC : Validation sensible à la casse pour la suppression d'utilisateur
    const deleteUserModal = document.getElementById('delete-user-modal');
    if (deleteUserModal) {
        const deleteForm = deleteUserModal.querySelector('form');
        const confirmInput = deleteUserModal.querySelector('#delete-confirm-input');
        const errorMessage = deleteUserModal.querySelector('#delete-error-message');

        deleteForm.addEventListener('submit', function(event) {
            // Comparaison stricte et sensible à la casse
            if (confirmInput.value.trim() !== this.dataset.username) {
                // Si ça ne correspond pas, on bloque l'envoi du formulaire
                event.preventDefault(); 
                errorMessage.textContent = 'Le nom de l\'utilisateur ne correspond pas.';
                confirmInput.focus();
            } else {
                errorMessage.textContent = '';
            }
        });
    }
	
	// =================================================================
	// SECTION 17 : GESTION DE L'AFFICHAGE DU NOM DE FICHIER POUR L'UPLOAD DE LOGO
	// =================================================================
    const editLogoInput = document.getElementById('edit_logo');
    if (editLogoInput) {
        const editLogoFilename = document.getElementById('edit-logo-filename');
        const defaultText = editLogoFilename.textContent;

        editLogoInput.addEventListener('change', function() {
            if (this.files.length > 0) {
                editLogoFilename.textContent = this.files[0].name;
            } else {
                editLogoFilename.textContent = defaultText;
            }
        });
    }
	
	// =================================================================
	// SECTION 18 : GESTION DE LA CONFIRMATION DE CLÔTURE DE BUDGET
	// =================================================================
    const clotureBtn = document.getElementById('cloture-budget-btn');
    if (clotureBtn) {
        clotureBtn.addEventListener('click', function() {
            const form = document.getElementById('cloture-budget-form');
            const modal = document.getElementById('cloture-budget-modal');
            const anneeSpan = document.getElementById('cloture-budget-annee');
            const confirmBtn = document.getElementById('confirm-cloture-btn');

            if (form && modal && anneeSpan && confirmBtn) {
                anneeSpan.textContent = form.dataset.annee;

                confirmBtn.onclick = () => {
                    form.submit();
                };

                modal.style.display = 'flex';
            }
        });
    }
});