(function () {
  if (
    document.querySelector(
      'script[src="https://cloud.umami.is/script.js"][data-website-id="677faf96-24fb-41fd-8edc-5a04c791ef9e"]',
    )
  ) {
    return;
  }

  const script = document.createElement("script");
  script.defer = true;
  script.src = "https://cloud.umami.is/script.js";
  script.setAttribute(
    "data-website-id",
    "677faf96-24fb-41fd-8edc-5a04c791ef9e",
  );
  document.head.appendChild(script);
})();
