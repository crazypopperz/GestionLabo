// =================================================================
// MODULE: CALENDAR MONTHLY VIEW (Version Finale et Robuste)
// Gère l'affichage et les interactions du calendrier mensuel.
// =================================================================
document.addEventListener("DOMContentLoaded", function () {
    const calendrierContainer = document.getElementById('calendrier-container');
    if (!calendrierContainer)
        return;

    const prevMonthBtn = document.getElementById('prev-month-btn');
    const nextMonthBtn = document.getElementById('next-month-btn');
    const currentMonthYear = document.getElementById('current-month-year');
    const calendrierGrid = calendrierContainer.querySelector('.calendrier-grid');

    let currentDate = new Date();

    async function renderCalendrier() {
        const year = currentDate.getFullYear();
        const month = currentDate.getMonth() + 1;

        const response = await fetch(`/api/reservations_par_mois/${year}/${month}`);
        const monthlyReservations = await response.json();

        calendrierGrid.innerHTML = '';

        const dayNames = ['Lun', 'Mar', 'Mer', 'Jeu', 'Ven', 'Sam', 'Dim'];
        dayNames.forEach(name => {
            const dayNameCell = document.createElement('div');
            dayNameCell.className = 'day-name';
            dayNameCell.textContent = name;
            calendrierGrid.appendChild(dayNameCell);
        });

        currentMonthYear.textContent = new Date(year, month - 1).toLocaleDateString('fr-FR', {
            month: 'long',
            year: 'numeric'
        });

        const firstDayOfMonth = new Date(year, month - 1, 1).getDay();
        const daysInMonth = new Date(year, month, 0).getDate();
        const dayOffset = (firstDayOfMonth === 0) ? 6 : firstDayOfMonth - 1;

        for (let i = 0; i < dayOffset; i++) {
            const emptyCell = document.createElement('div');
            emptyCell.className = 'day-cell other-month';
            calendrierGrid.appendChild(emptyCell);
        }

        // --- BLOC DE CODE CORRIGÉ ---
        const today = new Date();
        today.setHours(0, 0, 0, 0); // On ignore l'heure pour la comparaison

        for (let day = 1; day <= daysInMonth; day++) {
            const dateStr = `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
            const date = new Date(dateStr + "T00:00:00");
            
            const isPast = date < today;
            const isToday = date.getTime() === today.getTime();

            const dayCell = document.createElement('div');
            dayCell.className = 'day-cell';
            
            if (isPast) {
                dayCell.classList.add('past-day');
            } else {
                dayCell.classList.add('can-reserve');
            }
            
            if (isToday) {
                dayCell.classList.add('today');
            }

            dayCell.dataset.date = dateStr;

            let cellHTML = `<div class="day-number">${day}</div><div class="day-reservations"></div>`;
            if (monthlyReservations[dateStr] && monthlyReservations[dateStr].length > 0) {
                cellHTML += '<div class="activity-dot"></div>';
            }
            dayCell.innerHTML = cellHTML;
            calendrierGrid.appendChild(dayCell);
        }
        // --- FIN DU BLOC DE CODE CORRIGÉ ---
    }

    calendrierGrid.addEventListener('click', function (e) {
        const dayCell = e.target.closest('.day-cell.can-reserve');

        if (dayCell) {
            const dateStr = dayCell.dataset.date;
            if (dateStr) {
                window.location.href = `/jour/${dateStr}`;
            }
        }
    });

    prevMonthBtn.addEventListener('click', () => {
        currentDate.setMonth(currentDate.getMonth() - 1);
        renderCalendrier();
    });
    nextMonthBtn.addEventListener('click', () => {
        currentDate.setMonth(currentDate.getMonth() + 1);
        renderCalendrier();
    });

    renderCalendrier();
});