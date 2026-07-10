/* AB Test — help.html interactive layer.
   Same-origin external script (CSP script-src 'self'). Progressive enhancement:
   the page is fully usable without it; this only upgrades the marked widgets.
   No dependencies. */
(function () {
  "use strict";
  document.documentElement.classList.add("js");

  // ---- normal-distribution helpers ----
  function erf(x) {
    var s = x < 0 ? -1 : 1; x = Math.abs(x);
    var t = 1 / (1 + 0.3275911 * x);
    var y = 1 - (((((1.061405429 * t - 1.453152027) * t) + 1.421413741) * t - 0.284496736) * t + 0.254829592) * t * Math.exp(-x * x);
    return s * y;
  }
  function Phi(z) { return 0.5 * (1 + erf(z / Math.SQRT2)); }
  function pdf(x, mu, s) { return Math.exp(-((x - mu) * (x - mu)) / (2 * s * s)) / (s * Math.sqrt(2 * Math.PI)); }

  // ---- locale-aware number formatting ----
  // The page's lang attribute drives separators; Arabic pages keep Western digits
  // (the static text uses them too), hence the explicit nu-latn.
  var LOCALE = document.documentElement.lang || "en";
  if (LOCALE.indexOf("ar") === 0) LOCALE += "-u-nu-latn";
  var formatters = {};
  function nf(digits) {
    if (!formatters[digits]) {
      formatters[digits] = new Intl.NumberFormat(LOCALE, { minimumFractionDigits: digits, maximumFractionDigits: digits });
    }
    return formatters[digits];
  }
  function fmtFixed(n, digits) { return nf(digits).format(n); }
  function fmtInt(n) { return nf(0).format(n); }
  function fmtPct(p) { return fmtFixed(p * 100, p < 0.1 ? 2 : 1) + "%"; }

  // ============================================================
  // 1. Interactive power explorer
  // ============================================================
  (function powerExplorer() {
    var root = document.getElementById("powerExplorer");
    if (!root) return;
    var svg = root.querySelector("svg");
    var pathH0 = root.querySelector(".pe-h0");
    var pathH1 = root.querySelector(".pe-h1");
    var fillA = root.querySelector(".pe-alpha");
    var fillP = root.querySelector(".pe-power");
    var crit = root.querySelector(".pe-crit");
    var labA = root.querySelector(".pe-lab-a");
    var labP = root.querySelector(".pe-lab-pw");
    var labH1 = root.querySelector(".pe-lab-h1");
    var sEff = document.getElementById("peEffect");
    var sThr = document.getElementById("peThresh");
    var outAlpha = document.getElementById("peOutAlpha");
    var outPower = document.getElementById("peOutPower");
    var outZ = document.getElementById("peOutZ");
    var outEff = document.getElementById("peOutEff");

    var X0 = -4, X1 = 7, BASE = 205, TOP = 26, PEAK = 0.3989;
    function fx(x) { return (x - X0) / (X1 - X0) * 640; }
    function fy(d) { return BASE - (d / PEAK) * (BASE - TOP); }
    function curve(mu) {
      var p = "M", i, x;
      for (i = 0; i <= 110; i++) { x = X0 + (X1 - X0) * i / 110; p += " " + fx(x).toFixed(1) + "," + fy(pdf(x, mu, 1)).toFixed(1); }
      return p;
    }
    function tail(mu, z) { // area of N(mu,1) right of z, as closed path to baseline
      var p = "M " + fx(z).toFixed(1) + "," + BASE + " L " + fx(z).toFixed(1) + "," + fy(pdf(z, mu, 1)).toFixed(1), i, x;
      var n = 60;
      for (i = 1; i <= n; i++) { x = z + (X1 - z) * i / n; p += " L " + fx(x).toFixed(1) + "," + fy(pdf(x, mu, 1)).toFixed(1); }
      p += " L " + fx(X1).toFixed(1) + "," + BASE + " Z";
      return p;
    }
    function render() {
      var d = parseFloat(sEff.value);
      var z = parseFloat(sThr.value);
      var alpha = 1 - Phi(z);
      var power = 1 - Phi(z - d);
      pathH0.setAttribute("d", curve(0));
      pathH1.setAttribute("d", curve(d));
      fillA.setAttribute("d", tail(0, z));
      fillP.setAttribute("d", tail(d, z));
      crit.setAttribute("x1", fx(z)); crit.setAttribute("x2", fx(z));
      labH1.setAttribute("x", fx(d));
      // place α label just right of threshold near baseline; power label over H1 right side
      labA.setAttribute("x", fx(z) + 14); labA.setAttribute("y", BASE - 6);
      labP.setAttribute("x", fx(d) + 26); labP.setAttribute("y", fy(pdf(d + 0.6, d, 1)) + 6);
      if (outAlpha) outAlpha.textContent = fmtPct(alpha);
      if (outPower) outPower.textContent = fmtPct(power);
      if (outZ) outZ.textContent = fmtFixed(z, 2);
      if (outEff) outEff.textContent = fmtFixed(d, 1) + " σ";
    }
    sEff.addEventListener("input", render);
    sThr.addEventListener("input", render);
    render();
  })();

  // ============================================================
  // 2. Sample-size calculator (binary, 2 equal variants)
  // ============================================================
  (function sizer() {
    var root = document.getElementById("sizer");
    if (!root) return;
    var iBase = document.getElementById("szBase");
    var iMde = document.getElementById("szMde");
    var iAlpha = document.getElementById("szAlpha");
    var iPower = document.getElementById("szPower");
    var iTraffic = document.getElementById("szTraffic");
    var oPer = document.getElementById("szPer");
    var oTotal = document.getElementById("szTotal");
    var oDays = document.getElementById("szDays");
    var oNote = document.getElementById("szNote");

    function num(el, min, max, def) {
      var v = parseFloat(String(el.value).replace(",", "."));
      if (isNaN(v)) return def;
      return Math.min(max, Math.max(min, v));
    }
    function calc() {
      var p0 = num(iBase, 0.01, 99.9, 10) / 100;
      var mde = num(iMde, 0.1, 900, 10) / 100;
      var za = parseFloat(iAlpha.value);
      var zb = parseFloat(iPower.value);
      var p1 = p0 * (1 + mde);
      if (p1 >= 1) {
        oPer.textContent = "—"; oTotal.textContent = "—"; oDays.textContent = "—";
        oNote.hidden = false;
        return;
      }
      oNote.hidden = true;
      var delta = p1 - p0;
      var pbar = (p0 + p1) / 2;
      var num1 = za * Math.sqrt(2 * pbar * (1 - pbar)) + zb * Math.sqrt(p0 * (1 - p0) + p1 * (1 - p1));
      var n = Math.ceil((num1 * num1) / (delta * delta));
      oPer.textContent = fmtInt(n);
      oTotal.textContent = fmtInt(n * 2);
      var traffic = num(iTraffic, 1, 1e9, 5000);
      var perDay = traffic / 2; // two equal arms, 100% into the test
      var days = Math.ceil(n / perDay);
      oDays.textContent = fmtInt(days);
    }
    [iBase, iMde, iAlpha, iPower, iTraffic].forEach(function (el) {
      el.addEventListener("input", calc);
      el.addEventListener("change", calc);
    });
    calc();
  })();
})();
