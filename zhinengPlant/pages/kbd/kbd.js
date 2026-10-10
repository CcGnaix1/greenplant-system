// pages/kbd/kbd.js
const api = require('../../utils/request')
const { imageFor } = require('../../utils/plant-images')

Page({
  data: { d: {} },
  onLoad(opt) { this.id = opt.id || 1 },
  onShow() {
    api.call('/knowledge/detail', { data: { id: this.id } }).then(res => {
      const d = res.data || {}
      this.setData({ d: Object.assign({}, d, { image: imageFor(d.name) }) })
    })
  }
})
