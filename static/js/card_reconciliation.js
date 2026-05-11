(function () {
    document.addEventListener("submit", function (event) {
        var form = event.target.closest("[data-card-allocation-form]");
        if (!form) {
            return;
        }

        var amountInput = form.querySelector("[name='amount']");
        if (!amountInput) {
            return;
        }

        var maxAmount = Number(amountInput.getAttribute("data-unallocated-amount") || amountInput.getAttribute("max"));
        var enteredAmount = Number(amountInput.value);
        if (!Number.isFinite(maxAmount) || !Number.isFinite(enteredAmount)) {
            return;
        }

        if (enteredAmount > maxAmount) {
            event.preventDefault();
            amountInput.setCustomValidity("Allocation amount cannot exceed remaining unallocated amount.");
            amountInput.reportValidity();
        } else {
            amountInput.setCustomValidity("");
        }
    });
})();
