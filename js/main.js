const btn = document.getElementById("generar");
const audio = document.getElementById("audio");

btn.addEventListener("click", async () => {
  const texto = document.getElementById("texto").value;

  if (!texto.trim()) {
    alert("Por favor, escribe algo.");
    return;
  }

  try {
    const resp = await fetch("http://localhost:5000/audio", {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({ texto })
    });

    if (!resp.ok) {
      throw new Error("Error al generar audio");
    }

    const blob = await resp.blob();
    const url = URL.createObjectURL(blob);

    // Reproducir audio
    audio.src = url;
    audio.play();

    // Crear o actualizar el enlace de descarga
    let downloadLink = document.getElementById("link-descarga");

    if (!downloadLink) {
      downloadLink = document.createElement("a");
      downloadLink.id = "link-descarga";
      downloadLink.textContent = "Descargar audio";
      downloadLink.style.display = "block";
      document.body.appendChild(downloadLink);
    }

    downloadLink.href = url;
    downloadLink.download = "voz.mp3";

  } catch (err) {
    console.error(err);
    alert("Hubo un error generando el audio.");
  }
});
