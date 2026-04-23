package qa.qu.trakn.parentapp.data.api

import okhttp3.ResponseBody
import qa.qu.trakn.parentapp.data.models.GetApsResponse
import qa.qu.trakn.parentapp.data.models.HealthResponse
import qa.qu.trakn.parentapp.data.models.TagsResponse
import retrofit2.Response
import retrofit2.http.GET
import retrofit2.http.Header

interface ApiService {

    @GET("/health")
    suspend fun health(): HealthResponse

    @GET("/api/v1/venue/floor-plan")
    suspend fun getFloorPlan(): Response<ResponseBody>

    @GET("/api/v1/venue/aps")
    suspend fun getAps(
        @Header("X-API-Key") apiKey: String,
    ): GetApsResponse

    @GET("/api/v1/tags")
    suspend fun getTags(
        @Header("X-API-Key") apiKey: String,
    ): TagsResponse
}
