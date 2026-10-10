const images = {
  '绿萝': '/assets/plants/pothos.jpg',
  '龟背竹': '/assets/plants/monstera.jpg',
  '虎皮兰': '/assets/plants/sansevieria.jpg',
  '多肉': '/assets/plants/succulent.jpg',
  '发财树': '/assets/plants/pachira.jpg',
  '君子兰': '/assets/plants/clivia.jpg'
}

function imageFor(name) {
  return images[name] || '/assets/plants/pothos.jpg'
}

module.exports = { images, imageFor }
