// pages/timeline/timeline.js
const api = require('../../utils/request')

Page({
  data: { list: [] },
  onLoad(opt) { this.plantId = opt.id || 1 },
  onShow() {
    api.call('/plant/records', { data: { id: this.plantId } }).then(res => {
      this.setData({ list: res.data })
    })
  }
})
