// pages/detail/detail.js
const api = require('../../utils/request')

Page({
  data: { plant: {}, records: [] },
  onLoad(opt) { this.plantId = opt.id || 1 },
  onShow() {
    api.call('/plant/detail', { data: { id: this.plantId } }).then(res => {
      const plant = res.data
      plant.recordCount = this.data.records.length || 0
      this.setData({ plant })
    })
    api.call('/plant/records', { data: { id: this.plantId } }).then(res => {
      const records = res.data
      this.setData({
        records,
        'plant.recordCount': records.length
      })
    })
  },
  goRecord() { wx.navigateTo({ url: '/pages/record/record?id=' + this.plantId }) },
  goTimeline() { wx.navigateTo({ url: '/pages/timeline/timeline?id=' + this.plantId }) },
  goStats() { wx.navigateTo({ url: '/pages/stats/stats?id=' + this.plantId }) },
  goDiagnose() { wx.navigateTo({ url: '/pages/diagnose/diagnose?id=' + this.plantId }) },
  goAssign() { wx.navigateTo({ url: '/pages/assign/assign?id=' + this.plantId }) }
})
