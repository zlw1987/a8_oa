(function () {
    function closeAllMenus(exceptMenu) {
        document.querySelectorAll("[data-nav-menu]").forEach(function (menu) {
            if (menu === exceptMenu) {
                return;
            }
            menu.classList.remove("is-open");
            var trigger = menu.querySelector("[data-nav-trigger]");
            if (trigger) {
                trigger.setAttribute("aria-expanded", "false");
            }
        });
    }

    document.addEventListener("click", function (event) {
        var trigger = event.target.closest("[data-nav-trigger]");
        if (trigger) {
            var menu = trigger.closest("[data-nav-menu]");
            var isOpen = menu.classList.contains("is-open");
            closeAllMenus(menu);
            menu.classList.toggle("is-open", !isOpen);
            trigger.setAttribute("aria-expanded", String(!isOpen));
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
    });
})();
