(() => {
    const datePattern = /^(\d{4})-(\d{2})-(\d{2})$/;
    const germanDatePattern = /^(\d{2})\.(\d{2})\.(\d{4})$/;

    function toGermanDate(value) {
        const match = value.match(datePattern);
        return match ? `${match[3]}.${match[2]}.${match[1]}` : value;
    }

    function toIsoDate(value) {
        const germanMatch = value.match(germanDatePattern);
        if (germanMatch) {
            return `${germanMatch[3]}-${germanMatch[2]}-${germanMatch[1]}`;
        }

        return value;
    }

    function parseDate(value) {
        const isoValue = toIsoDate(value);
        const match = isoValue.match(datePattern);
        if (!match) {
            return new Date();
        }

        const date = new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]));
        return Number.isNaN(date.getTime()) ? new Date() : date;
    }

    function pad(value) {
        return String(value).padStart(2, '0');
    }

    function formatLocalDate(date) {
        return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
    }

    function setupDatePicker(input, wrapper, popup) {
        let visibleMonth = parseDate(input.value);

        function render() {
            const year = visibleMonth.getFullYear();
            const month = visibleMonth.getMonth();
            const firstWeekday = (new Date(year, month, 1).getDay() + 6) % 7;
            const daysInMonth = new Date(year, month + 1, 0).getDate();
            const selectedValue = toIsoDate(input.value);
            const today = new Date();
            const weekdays = ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So'];

            popup.innerHTML = `
                <div class="picker-heading">
                    <button type="button" class="picker-nav" data-month="-1" aria-label="Vorheriger Monat">‹</button>
                    <strong>${new Intl.DateTimeFormat('de-DE', { month: 'long', year: 'numeric' }).format(visibleMonth)}</strong>
                    <button type="button" class="picker-nav" data-month="1" aria-label="Nächster Monat">›</button>
                </div>
                <div class="calendar-grid" role="grid" aria-label="Kalender">
                    ${weekdays.map((day) => `<span class="calendar-weekday">${day}</span>`).join('')}
                    ${Array.from({ length: firstWeekday }, () => '<span class="calendar-empty"></span>').join('')}
                    ${Array.from({ length: daysInMonth }, (_, index) => {
                        const day = index + 1;
                        const value = `${year}-${pad(month + 1)}-${pad(day)}`;
                        const isSelected = value === selectedValue;
                        const isToday = year === today.getFullYear()
                            && month === today.getMonth()
                            && day === today.getDate();
                        const classes = ['calendar-day', isToday ? 'is-today' : '', isSelected ? 'is-selected' : '']
                            .filter(Boolean)
                            .join(' ');
                        return `<button type="button" class="${classes}" data-date="${value}" aria-pressed="${isSelected}">${day}</button>`;
                    }).join('')}
                </div>
                <button type="button" class="picker-quick-action" data-action="today">Heute</button>`;
        }

        popup.addEventListener('click', (event) => {
            const button = event.target.closest('button');
            if (!button) return;
            event.stopPropagation();

            if (button.dataset.month) {
                visibleMonth = new Date(
                    visibleMonth.getFullYear(),
                    visibleMonth.getMonth() + Number(button.dataset.month),
                    1
                );
                render();
                return;
            }

            const selectedDate = button.dataset.date
                || (button.dataset.action === 'today' ? toIsoDate(formatLocalDate(new Date())) : '');
            if (selectedDate) {
                input.value = toGermanDate(selectedDate);
                input.dispatchEvent(new Event('input', { bubbles: true }));
                input.dispatchEvent(new Event('change', { bubbles: true }));
                wrapper.classList.remove('is-open');
            }
        });

        input.addEventListener('focus', () => {
            visibleMonth = parseDate(input.value);
        });

        return () => {
            render();
        };
    }

    function setupTimePicker(input, wrapper, popup) {
        const initialTime = /^(\d{2}):(\d{2})/.exec(input.value);
        const initialHour = initialTime ? Number(initialTime[1]) : 9;
        const initialMinute = initialTime ? Number(initialTime[2]) : 0;

        popup.innerHTML = `
            <div class="picker-heading"><strong>Uhrzeit auswählen</strong></div>
            <div class="time-picker-fields">
                <label>Stunde
                    <select class="time-hour" aria-label="Stunde">
                        ${Array.from({ length: 24 }, (_, hour) => `<option value="${pad(hour)}">${pad(hour)}</option>`).join('')}
                    </select>
                </label>
                <span class="time-separator">:</span>
                <label>Minute
                    <select class="time-minute" aria-label="Minute">
                        ${Array.from({ length: 60 }, (_, minute) => `<option value="${pad(minute)}">${pad(minute)}</option>`).join('')}
                    </select>
                </label>
            </div>
            <button type="button" class="picker-quick-action time-picker-now">Jetzt</button>
            <button type="button" class="primary-button time-picker-apply">Uhrzeit übernehmen</button>`;

        const hourSelect = popup.querySelector('.time-hour');
        const minuteSelect = popup.querySelector('.time-minute');
        hourSelect.value = pad(initialHour);
        minuteSelect.value = pad(initialMinute);

        const syncTime = () => {
            const match = /^(\d{2}):(\d{2})/.exec(input.value);
            if (match) {
                hourSelect.value = match[1];
                minuteSelect.value = match[2];
            }
        };
        input.addEventListener('focus', syncTime);

        popup.querySelector('.time-picker-now').addEventListener('click', () => {
            const now = new Date();
            input.value = `${pad(now.getHours())}:${pad(now.getMinutes())}`;
            input.dispatchEvent(new Event('input', { bubbles: true }));
            input.dispatchEvent(new Event('change', { bubbles: true }));
            wrapper.classList.remove('is-open');
        });

        popup.querySelector('.time-picker-apply').addEventListener('click', () => {
            input.value = `${hourSelect.value}:${minuteSelect.value}`;
            input.dispatchEvent(new Event('input', { bubbles: true }));
            input.dispatchEvent(new Event('change', { bubbles: true }));
            wrapper.classList.remove('is-open');
        });

        return syncTime;
    }

    document.querySelectorAll(
        '.form-card input[type="date"], .form-card input[type="time"], .filter-bar input[type="date"]'
    ).forEach((input) => {
        const type = input.type;
        const wrapper = document.createElement('div');
        wrapper.className = 'picker-field';
        input.parentNode.insertBefore(wrapper, input);
        wrapper.append(input);

        if (type === 'date') {
            input.type = 'text';
            input.value = toGermanDate(input.value);
            input.placeholder = 'TT.MM.JJJJ';
            input.setAttribute('inputmode', 'numeric');
            input.setAttribute('autocomplete', 'off');
        } else {
            input.type = 'text';
            input.placeholder = 'HH:MM';
            input.setAttribute('inputmode', 'numeric');
            input.setAttribute('autocomplete', 'off');
        }

        const popup = document.createElement('div');
        popup.className = `picker-popover ${type}-picker`;
        popup.setAttribute('role', 'dialog');
        popup.setAttribute('aria-label', type === 'date' ? 'Kalender' : 'Uhrzeit auswählen');
        wrapper.append(popup);

        const render = type === 'date'
            ? setupDatePicker(input, wrapper, popup)
            : setupTimePicker(input, wrapper, popup);

        const toggle = () => {
            if (wrapper.classList.contains('is-open')) {
                wrapper.classList.remove('is-open');
                return;
            }

            document.querySelectorAll('.picker-field.is-open').forEach((openPicker) => {
                openPicker.classList.remove('is-open');
            });
            render();
            wrapper.classList.add('is-open');
        };

        const trigger = document.createElement('button');
        trigger.type = 'button';
        trigger.className = 'picker-trigger';
        trigger.setAttribute('aria-label', type === 'date' ? 'Kalender öffnen' : 'Uhrzeit auswählen');
        trigger.textContent = type === 'date' ? '▦' : '◷';
        trigger.addEventListener('click', toggle);
        input.addEventListener('click', toggle);
        wrapper.append(trigger);
    });

    document.addEventListener('click', (event) => {
        const eventPath = event.composedPath();
        document.querySelectorAll('.picker-field.is-open').forEach((wrapper) => {
            if (!eventPath.includes(wrapper)) {
                wrapper.classList.remove('is-open');
            }
        });
    });

    document.addEventListener('keydown', (event) => {
        if (event.key === 'Escape') {
            document.querySelectorAll('.picker-field.is-open').forEach((wrapper) => {
                wrapper.classList.remove('is-open');
            });
        }
    });

    document.querySelectorAll('.form-card form, .filter-bar').forEach((form) => {
        form.addEventListener('submit', () => {
            form.querySelectorAll('.picker-field input[placeholder="TT.MM.JJJJ"]').forEach((input) => {
                input.value = toIsoDate(input.value);
            });
        });
    });
})();
