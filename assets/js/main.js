// Mobile menu toggle
const menuToggle = document.getElementById("menu-toggle");
const mobileMenu = document.getElementById("mobile-menu");
const iconMenu = document.getElementById("icon-menu");
const iconClose = document.getElementById("icon-close");

if (menuToggle && mobileMenu) {
  menuToggle.addEventListener("click", () => {
    const isOpen = !mobileMenu.classList.contains("hidden");
    mobileMenu.classList.toggle("hidden");
    iconMenu.classList.toggle("hidden");
    iconClose.classList.toggle("hidden");
    menuToggle.setAttribute("aria-expanded", String(!isOpen));
  });
}

// Sticky header shadow on scroll
const header = document.getElementById("site-header");
if (header) {
  window.addEventListener("scroll", () => {
    if (window.scrollY > 8) {
      header.classList.add("shadow-md");
    } else {
      header.classList.remove("shadow-md");
    }
  });
}

// Donate page: one-time / monthly tabs + amount selection
const tabOnce = document.getElementById("tab-once");
const tabMonthly = document.getElementById("tab-monthly");
const amountButtons = document.querySelectorAll(".amount-btn");
const customAmountInput = document.getElementById("custom-amount");
const impactNote = document.getElementById("impact-note");
const donateCta = document.getElementById("donate-cta");

if (tabOnce && tabMonthly) {
  let frequency = "once";
  let selectedAmount = null;

  const impactMessages = {
    25: "$25 provides one art therapy session for a child.",
    50: "$50 provides a Hibuki therapy doll for a child in need.",
    100: "$100 covers a week of group sensory play sessions.",
  };

  function setFrequency(freq) {
    frequency = freq;
    tabOnce.setAttribute("aria-selected", String(freq === "once"));
    tabMonthly.setAttribute("aria-selected", String(freq === "monthly"));
    updateCta();
  }

  function updateCta() {
    const amount = selectedAmount === "custom"
      ? (customAmountInput.value || "0")
      : selectedAmount;

    if (amount && amount !== "custom") {
      const suffix = frequency === "monthly" ? "/month" : " Now";
      donateCta.textContent = `Donate $${amount}${suffix}`;
    } else {
      donateCta.textContent = "Donate Now";
    }

    if (impactMessages[selectedAmount]) {
      impactNote.textContent = impactMessages[selectedAmount];
    } else if (selectedAmount === "custom") {
      impactNote.textContent = "Every dollar helps a child access free therapy.";
    } else {
      impactNote.textContent = "Select an amount to see your impact.";
    }
  }

  tabOnce.addEventListener("click", () => setFrequency("once"));
  tabMonthly.addEventListener("click", () => setFrequency("monthly"));

  amountButtons.forEach((btn) => {
    btn.addEventListener("click", () => {
      amountButtons.forEach((b) => b.classList.remove("is-active"));
      btn.classList.add("is-active");
      selectedAmount = btn.dataset.amount;
      if (selectedAmount !== "custom") {
        customAmountInput.value = "";
      }
      updateCta();
    });
  });

  if (customAmountInput) {
    customAmountInput.addEventListener("input", () => {
      if (selectedAmount === "custom") {
        updateCta();
      }
    });
  }
}
