(function () {
    var hoverOpenDelay = 75;
    var hoverCloseDelay = 200;
    var hoverTimers = new WeakMap();

    function getTimerState(menu) {
        if (!hoverTimers.has(menu)) {
            hoverTimers.set(menu, {});
        }
        return hoverTimers.get(menu);
    }

    function setMenuOpen(menu, isOpen) {
        menu.classList.toggle("is-open", isOpen);
        var trigger = menu.querySelector("[data-nav-trigger]");
        if (trigger) {
            trigger.setAttribute("aria-expanded", String(isOpen));
        }
    }

    function closeAllMenus(exceptMenu) {
        document.querySelectorAll("[data-nav-menu]").forEach(function (menu) {
            if (menu === exceptMenu) {
                return;
            }
            setMenuOpen(menu, false);
        });
    }

    function scheduleOpen(menu) {
        var timerState = getTimerState(menu);
        window.clearTimeout(timerState.closeTimer);
        timerState.openTimer = window.setTimeout(function () {
            closeAllMenus(menu);
            setMenuOpen(menu, true);
        }, hoverOpenDelay);
    }

    function scheduleClose(menu) {
        var timerState = getTimerState(menu);
        window.clearTimeout(timerState.openTimer);
        timerState.closeTimer = window.setTimeout(function () {
            setMenuOpen(menu, false);
        }, hoverCloseDelay);
    }

    document.addEventListener("click", function (event) {
        var trigger = event.target.closest("[data-nav-trigger]");
        if (trigger) {
            var menu = trigger.closest("[data-nav-menu]");
            var isOpen = menu.classList.contains("is-open");
            closeAllMenus(menu);
            setMenuOpen(menu, !isOpen);
            return;
        }

        if (!event.target.closest("[data-nav-menu]")) {
            closeAllMenus();
        }
    });

    document.addEventListener("keydown", function (event) {
        if (event.key === "Escape") {
            closeAllMenus();
        }

        var trigger = event.target.closest("[data-nav-trigger]");
        if (trigger && (event.key === "Enter" || event.key === " ")) {
            event.preventDefault();
            var menu = trigger.closest("[data-nav-menu]");
            var isOpen = menu.classList.contains("is-open");
            closeAllMenus(menu);
            setMenuOpen(menu, !isOpen);
        }
    });

    document.querySelectorAll("[data-nav-menu]").forEach(function (menu) {
        menu.addEventListener("mouseenter", function () {
            scheduleOpen(menu);
        });
        menu.addEventListener("mouseleave", function () {
            scheduleClose(menu);
        });
    });
})();
