window.onhashchange = function(e) {
        if(location.hash.length < 2)
                return;
        if($(window).scrollTop() + 110 > $(location.hash).offset().top)
                window.scrollBy(0, -110);
        $(location.hash).css("color", "#2f96b4").delay(2000).animate({"color" : "#333333"}, 2000);
}