window.CSInterface = function () {
    return {
      evalScript: function (script, callback) {
        console.log("Simulando envío a AE:", script);
        setTimeout(() => {
          callback && callback("Simulación completa ✔️");
        }, 500);
      }
    };
  };
  